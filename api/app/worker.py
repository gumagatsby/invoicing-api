"""Background worker (arq). Every few seconds it sends webhook deliveries that are due.
Polling the outbox table means a crash between saving an event and sending it loses nothing."""
from datetime import UTC, datetime

import httpx
from arq import cron
from arq.connections import RedisSettings
from prometheus_client import start_http_server
from sqlalchemy import select

from .config import settings
from .db import SessionLocal
from .metrics import WEBHOOKS
from .models import WebhookDelivery
from .services.webhooks import deliver


async def send_due(ctx) -> int:
    async with SessionLocal() as session:
        due = (await session.execute(select(WebhookDelivery.id).where(
            WebhookDelivery.status == "pending", WebhookDelivery.next_attempt_at <= datetime.now(UTC)
        ).order_by(WebhookDelivery.created_at).limit(100))).scalars().all()
    for delivery_id in due:
        async with SessionLocal() as session:
            result = await deliver(session, delivery_id, ctx["http"], settings().webhook_max_attempts)
        WEBHOOKS.labels(result="retry" if result == "pending" else result).inc()
    return len(due)


async def startup(ctx):
    start_http_server(9100)  # Prometheus scrapes the worker here
    ctx["http"] = httpx.AsyncClient(follow_redirects=False)


async def shutdown(ctx):
    await ctx["http"].aclose()


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings().redis_url)
    cron_jobs = [cron(send_due, second=set(range(0, 60, 5)), run_at_startup=True)]
    on_startup = startup
    on_shutdown = shutdown
