import asyncio
import json
import time
import uuid

import httpx
import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import WebhookDelivery
from app.services import webhooks
from conftest import invoice, merchant


def test_signature_round_trip_and_replay_window():
    body = b'{"type":"invoice.paid"}'
    now = int(time.time())
    header = webhooks.sign("whsec_x", body, now)
    assert webhooks.verify("whsec_x", body, header, now=now)
    assert not webhooks.verify("whsec_other", body, header, now=now)
    assert not webhooks.verify("whsec_x", body + b" ", header, now=now)
    assert not webhooks.verify("whsec_x", body, header, now=now + 301)  # too old: replay


async def _deliveries(endpoint_id):
    async with SessionLocal() as s:
        return (await s.execute(select(WebhookDelivery).where(WebhookDelivery.endpoint_id == uuid.UUID(endpoint_id)))).scalars().all()


async def test_payment_records_signed_deliveries(client):
    h = await merchant(client)
    ep = (await client.post("/webhooks", json={"url": "https://hooks.example.com/in"}, headers=h)).json()
    assert ep["secret"].startswith("whsec_")
    inv = await invoice(client, h, 1_000)
    await client.post(f"/invoices/{inv['id']}/payments", headers={**h, "Idempotency-Key": uuid.uuid4().hex},
                      json={"amount_minor": 1_000, "currency": "GBP"})
    ds = await _deliveries(ep["id"])
    assert sorted(d.event for d in ds) == ["invoice.paid", "payment.succeeded"]

    received = []

    def ok(request: httpx.Request):
        received.append(request)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(ok)) as http:
        for d in ds:
            async with SessionLocal() as s:
                assert await webhooks.deliver(s, d.id, http, 6) == "delivered"
    sig = received[0].headers[webhooks.SIGNATURE_HEADER]
    assert webhooks.verify(ep["secret"], received[0].content, sig)
    assert json.loads(received[0].content)["data"]["invoice_id"] == inv["id"]


async def test_failing_endpoint_retries_then_fails(client):
    h = await merchant(client)
    ep = (await client.post("/webhooks", json={"url": "https://down.example.com/in"}, headers=h)).json()
    inv = await invoice(client, h, 1_000)
    await client.post(f"/invoices/{inv['id']}/payments", headers={**h, "Idempotency-Key": uuid.uuid4().hex},
                      json={"amount_minor": 500, "currency": "GBP"})
    d = (await _deliveries(ep["id"]))[0]
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(503))) as http:
        results = []
        for _ in range(3):
            async with SessionLocal() as s:
                results.append(await webhooks.deliver(s, d.id, http, 3))
    assert results == ["pending", "pending", "failed"]
    d = [x for x in await _deliveries(ep["id"]) if x.id == d.id][0]
    assert d.attempts == 3 and d.last_status_code == 503


async def test_webhook_urls_must_point_at_public_addresses(client):
    h = await merchant(client)
    for url in ["http://127.0.0.1/in", "http://localhost:8000/in", "http://169.254.169.254/latest/meta-data/",
                "http://10.0.0.5/in", "http://[::1]/in", "http://[::ffff:192.168.1.1]/in", "http://api.localhost/in"]:
        r = await client.post("/webhooks", json={"url": url}, headers=h)
        assert r.status_code == 422, url
        assert r.json()["detail"] == "The webhook URL must point at a public address"
    assert (await client.post("/webhooks", json={"url": "https://hooks.example.com/in"}, headers=h)).status_code == 201


async def _local_server():
    """A real HTTP server on 127.0.0.1 that answers 204, to prove what the guarded client will and will not reach."""
    async def answer(reader, writer):
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        await writer.drain()
        writer.close()
    server = await asyncio.start_server(answer, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


async def test_worker_refuses_to_connect_to_private_addresses():
    server, port = await _local_server()
    async with server:
        # A hostname that resolves to loopback is refused at connection time, even though the server is listening
        async with webhooks.http_client(allowed=[]) as http:
            with pytest.raises(httpx.ConnectError, match="not public"):
                await http.post(f"http://localhost:{port}/in", content=b"{}")
        # An allowed host gets through, which shows the refusal above came from the guard
        async with webhooks.http_client(allowed=["localhost"]) as http:
            assert (await http.post(f"http://localhost:{port}/in", content=b"{}")).status_code == 204

