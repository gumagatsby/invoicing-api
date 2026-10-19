from datetime import date

from app import demo


async def test_demo_account_rebuilds_cleanly_and_balances(client):
    # Run twice: the second run must replace the first, not add to it.
    await demo.seed(client, today=date(2026, 10, 19))
    await demo.seed(client, today=date(2026, 10, 19))

    r = await client.post("/auth/token", data={"username": demo.DEMO_EMAIL, "password": demo.DEMO_PASSWORD})
    assert r.status_code == 200
    auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

    invoices = (await client.get("/invoices?limit=100", headers=auth)).json()["items"]
    assert len(invoices) == len(demo.INVOICES)
    assert sorted(i["status"] for i in invoices) == sorted(["void", "paid", "open", "paid", "open", "open", "open", "open"])
    # Newest first, with the dates moved back: the oldest invoice was issued 76 days ago.
    assert invoices[-1]["created_at"] < invoices[0]["created_at"]

    balances = (await client.get("/ledger/balances", headers=auth)).json()
    assert balances and all(acc["_balanced"] for acc in balances.values())

    endpoints = (await client.get("/webhooks", headers=auth)).json()
    assert [e["url"] for e in endpoints] == [demo.RECEIVER_URL]
    deliveries = (await client.get(f"/webhooks/{endpoints[0]['id']}/deliveries", headers=auth)).json()
    # Four payments, two of which settle their invoice.
    assert sorted(d["event"] for d in deliveries) == ["invoice.paid"] * 2 + ["payment.succeeded"] * 4
