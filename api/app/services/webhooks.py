"""Outgoing webhooks: recorded with the event (outbox), signed, delivered by the worker with retries."""
import asyncio
import hashlib
import hmac
import ipaddress
import json
import secrets
import socket
import time
import uuid
from datetime import UTC, datetime, timedelta

import httpcore
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import WebhookDelivery, WebhookEndpoint

SIGNATURE_HEADER = "Invoicing-Signature"


# ---------- Server-side request forgery ----------
# A merchant chooses the URL the worker posts to, so without a check they could point it at
# localhost, the cloud metadata service (169.254.169.254) or another container on our network.

def is_public(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


def allowed_url_host(host: str, allowed: list[str] | None = None) -> bool:
    """The check when an endpoint is saved: no localhost and no private IP written into the URL.
    Hostnames are not resolved here, because a merchant's DNS may not be live yet; the worker checks every connection."""
    host = host.strip("[]").lower()
    if host in (allowed if allowed is not None else settings().webhook_allowed_hosts):
        return True
    if host == "localhost" or host.endswith(".localhost"):
        return False
    try:
        return is_public(host)
    except ValueError:
        return True  # a hostname


class BlockedAddress(httpcore.ConnectError):
    pass


class GuardedBackend(httpcore.AsyncNetworkBackend):
    """Resolves the host itself, refuses any address that is not public, then connects to the address it checked,
    so DNS cannot answer differently between the check and the connection."""

    def __init__(self, allowed: list[str]):
        self.allowed, self.inner = set(allowed), httpcore.AnyIOBackend()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
        ips = [info[4][0] for info in infos]
        if host not in self.allowed and not all(is_public(ip) for ip in ips):
            raise BlockedAddress(f"{host} resolves to an address that is not public")
        error = None
        for ip in dict.fromkeys(ips):  # each checked address in turn, as a normal client would
            try:
                return await self.inner.connect_tcp(ip, port, timeout, local_address, socket_options)
            except httpcore.ConnectError as e:
                error = e
        raise error or httpcore.ConnectError(f"{host} did not resolve")

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise BlockedAddress("Unix sockets are not allowed")

    async def sleep(self, seconds):
        await self.inner.sleep(seconds)


def http_client(allowed: list[str] | None = None) -> httpx.AsyncClient:
    """The worker's client: no redirects, no proxies from the environment, and every connection checked."""
    transport = httpx.AsyncHTTPTransport(trust_env=False)
    # httpx 0.28 has no option for the network backend, so the pool is rebuilt with the same TLS settings.
    # tests/test_webhooks.py proves the guard is in the path, so an httpx upgrade that breaks this fails CI.
    transport._pool = httpcore.AsyncConnectionPool(
        ssl_context=transport._pool._ssl_context,
        network_backend=GuardedBackend(allowed if allowed is not None else settings().webhook_allowed_hosts))
    return httpx.AsyncClient(transport=transport, follow_redirects=False, trust_env=False)


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
