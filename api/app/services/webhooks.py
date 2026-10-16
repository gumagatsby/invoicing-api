"""Outgoing webhooks: recorded with the event (outbox), signed, delivered by the worker with retries."""
import hashlib
import hmac
import json
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import WebhookDelivery, WebhookEndpoint

SIGNATURE_HEADER = "Invoicing-Signature"


def new_secret() -> str:
    return "whsec_" + secrets.token_hex(24)


def sign(secret: str, body: bytes, timestamp: int) -> str:
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={mac}"


def verify(secret: str, body: bytes, header: str, tolerance: int = 300, now: int | None = None) -> bool:
    """What a receiver runs. Rejects a bad signature and anything older than the tolerance (replays)."""
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts = int(parts["t"])
    except (ValueError, KeyError):
        return False
    if abs((now or int(time.time())) - ts) > tolerance:
        return False
    return hmac.compare_digest(sign(secret, body, ts), header)


async def record(session: AsyncSession, owner_id: uuid.UUID, event: str, data: dict) -> None:
    endpoints = (await session.execute(
        select(WebhookEndpoint).where(WebhookEndpoint.owner_id == owner_id, WebhookEndpoint.active.is_(True))
    )).scalars().all()
    for ep in endpoints:
        session.add(WebhookDelivery(endpoint_id=ep.id, event=event,
                                    payload={"id": str(uuid.uuid4()), "type": event, "data": data,
                                             "created": int(time.time())}))


def backoff(attempt: int) -> timedelta:
    """1, 2, 4, 8, 16 minutes between attempts."""
    return timedelta(minutes=2 ** (attempt - 1))


async def deliver(session: AsyncSession, delivery_id: uuid.UUID, client: httpx.AsyncClient, max_attempts: int) -> str:
    """One attempt. Returns the delivery's new status."""
    async with session.begin():
        d = (await session.execute(select(WebhookDelivery).where(WebhookDelivery.id == delivery_id)
                                   .with_for_update(skip_locked=True))).scalar_one_or_none()
        if d is None or d.status != "pending":
            return d.status if d else "missing"
        ep = await session.get(WebhookEndpoint, d.endpoint_id)
        body = json.dumps(d.payload, separators=(",", ":")).encode()
        d.attempts += 1
        try:
            resp = await client.post(ep.url, content=body, timeout=10, headers={
                "Content-Type": "application/json", SIGNATURE_HEADER: sign(ep.secret, body, int(time.time()))})
            d.last_status_code = resp.status_code
            ok = 200 <= resp.status_code < 300
        except httpx.HTTPError:
            d.last_status_code, ok = None, False
        if ok:
            d.status = "delivered"
        elif d.attempts >= max_attempts:
            d.status = "failed"
        else:
            d.next_attempt_at = datetime.now(UTC) + backoff(d.attempts)
        return d.status
