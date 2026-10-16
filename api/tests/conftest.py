import os
import uuid

os.environ.setdefault("APP_DATABASE_URL", "postgresql+asyncpg://invoicing:invoicing@localhost:5432/invoicing_test")
os.environ.setdefault("APP_REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("APP_JWT_SECRET", "test-only-secret-" + "x" * 32)
os.environ.setdefault("APP_RATE_LIMIT_PER_MINUTE", "100000")

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.deps import redis  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
async def schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await redis().flushdb()
    yield
    await engine.dispose()


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def merchant(client) -> dict:
    """Register and log in a fresh merchant; returns auth headers."""
    email = f"m-{uuid.uuid4().hex[:10]}@example.com"
    r = await client.post("/auth/register", json={"email": email, "password": "correct horse battery"})
    assert r.status_code == 201, r.text
    r = await client.post("/auth/token", data={"username": email, "password": "correct horse battery"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def invoice(client, headers, amount=10_000, currency="GBP") -> dict:
    c = await client.post("/customers", json={"name": "Acme Ltd", "email": "ap@acme.example"}, headers=headers)
    r = await client.post("/invoices", headers=headers, json={
        "customer_id": c.json()["id"], "currency": currency, "due_date": "2026-12-31",
        "lines": [{"description": "Consulting", "quantity": 1, "unit_price_minor": amount}]})
    assert r.status_code == 201, r.text
    return r.json()
