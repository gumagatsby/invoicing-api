import asyncio
import uuid

from conftest import invoice, merchant


def key():
    return {"Idempotency-Key": uuid.uuid4().hex}


async def test_invoice_total_from_lines(client):
    h = await merchant(client)
    c = await client.post("/customers", json={"name": "Acme", "email": "ap@acme.example"}, headers=h)
    r = await client.post("/invoices", headers=h, json={"customer_id": c.json()["id"], "currency": "EUR", "due_date": "2026-12-31",
                                                       "lines": [{"description": "A", "quantity": 3, "unit_price_minor": 1250},
                                                                 {"description": "B", "quantity": 1, "unit_price_minor": 500}]})
    assert r.json()["total_minor"] == 4250 and r.json()["outstanding_minor"] == 4250


async def test_merchants_cannot_see_each_others_invoices(client):
    a, b = await merchant(client), await merchant(client)
    inv = await invoice(client, a)
    assert (await client.get(f"/invoices/{inv['id']}", headers=b)).status_code == 404
    assert (await client.post(f"/invoices/{inv['id']}/payments", headers={**b, **key()},
                              json={"amount_minor": 100, "currency": "GBP"})).status_code == 404


async def test_partial_then_full_payment_marks_paid(client):
    h = await merchant(client)
    inv = await invoice(client, h, 10_000)
    for amount in (4_000, 6_000):
        r = await client.post(f"/invoices/{inv['id']}/payments", headers={**h, **key()}, json={"amount_minor": amount, "currency": "GBP"})
        assert r.status_code == 201
    got = (await client.get(f"/invoices/{inv['id']}", headers=h)).json()
    assert got["status"] == "paid" and got["outstanding_minor"] == 0


async def test_overpayment_and_wrong_currency_rejected(client):
    h = await merchant(client)
    inv = await invoice(client, h, 1_000)
    assert (await client.post(f"/invoices/{inv['id']}/payments", headers={**h, **key()},
                              json={"amount_minor": 1_001, "currency": "GBP"})).status_code == 422
    assert (await client.post(f"/invoices/{inv['id']}/payments", headers={**h, **key()},
                              json={"amount_minor": 100, "currency": "USD"})).status_code == 422


async def test_idempotent_replay_returns_same_payment(client):
    h = await merchant(client)
    inv = await invoice(client, h, 5_000)
    k = key()
    first = await client.post(f"/invoices/{inv['id']}/payments", headers={**h, **k}, json={"amount_minor": 2_000, "currency": "GBP"})
    again = await client.post(f"/invoices/{inv['id']}/payments", headers={**h, **k}, json={"amount_minor": 2_000, "currency": "GBP"})
    assert first.status_code == 201 and again.status_code == 200
    assert again.headers["Idempotent-Replayed"] == "true" and again.json()["id"] == first.json()["id"]
    assert (await client.get(f"/invoices/{inv['id']}", headers=h)).json()["paid_minor"] == 2_000


async def test_same_key_different_body_is_conflict(client):
    h = await merchant(client)
    inv = await invoice(client, h, 5_000)
    k = key()
    await client.post(f"/invoices/{inv['id']}/payments", headers={**h, **k}, json={"amount_minor": 2_000, "currency": "GBP"})
    r = await client.post(f"/invoices/{inv['id']}/payments", headers={**h, **k}, json={"amount_minor": 3_000, "currency": "GBP"})
    assert r.status_code == 409


async def test_twenty_concurrent_retries_create_one_payment(client):
    h = await merchant(client)
    inv = await invoice(client, h, 5_000)
    k = key()
    rs = await asyncio.gather(*[client.post(f"/invoices/{inv['id']}/payments", headers={**h, **k},
                                            json={"amount_minor": 5_000, "currency": "GBP"}) for _ in range(20)])
    assert sorted(r.status_code for r in rs) == [200] * 19 + [201]
    assert len({r.json()["id"] for r in rs}) == 1
    assert len((await client.get(f"/invoices/{inv['id']}/payments", headers=h)).json()) == 1


async def test_concurrent_full_payments_cannot_overpay(client):
    h = await merchant(client)
    inv = await invoice(client, h, 5_000)
    rs = await asyncio.gather(*[client.post(f"/invoices/{inv['id']}/payments", headers={**h, **key()},
                                            json={"amount_minor": 5_000, "currency": "GBP"}) for _ in range(10)])
    assert sorted(r.status_code for r in rs) == [201] + [422] * 9
    assert (await client.get(f"/invoices/{inv['id']}", headers=h)).json()["paid_minor"] == 5_000


async def test_ledger_always_balances(client):
    h = await merchant(client)
    paid = await invoice(client, h, 3_000)
    await client.post(f"/invoices/{paid['id']}/payments", headers={**h, **key()}, json={"amount_minor": 3_000, "currency": "GBP"})
    voided = await invoice(client, h, 700)
    assert (await client.post(f"/invoices/{voided['id']}/void", headers=h)).status_code == 200
    b = (await client.get("/ledger/balances", headers=h)).json()["GBP"]
    assert b["_balanced"] is True
    assert b["cash"]["balance_minor"] == 3_000 and b["receivables"]["balance_minor"] == 0
    assert b["revenue"]["balance_minor"] == -3_000  # credit balance: revenue earned


async def test_cannot_void_a_part_paid_invoice(client):
    h = await merchant(client)
    inv = await invoice(client, h, 3_000)
    await client.post(f"/invoices/{inv['id']}/payments", headers={**h, **key()}, json={"amount_minor": 1, "currency": "GBP"})
    assert (await client.post(f"/invoices/{inv['id']}/void", headers=h)).status_code == 422


async def test_pagination_walks_every_invoice_once(client):
    h = await merchant(client)
    made = {(await invoice(client, h, 100 + i))["id"] for i in range(7)}
    seen, cursor = [], None
    while True:
        r = (await client.get("/invoices", params={"limit": 3, **({"cursor": cursor} if cursor else {})}, headers=h)).json()
        seen += [i["id"] for i in r["items"]]
        cursor = r["next_cursor"]
        if not cursor:
            break
    assert len(seen) == 7 and set(seen) == made


async def test_rate_limit_returns_429(client):
    from app.config import settings
    h = await merchant(client)
    old = settings().rate_limit_per_minute
    settings().rate_limit_per_minute = 3
    try:
        codes = [(await client.get("/customers", headers=h)).status_code for _ in range(5)]
    finally:
        settings().rate_limit_per_minute = old
    assert codes[:3] == [200] * 3 and codes[3] == 429
