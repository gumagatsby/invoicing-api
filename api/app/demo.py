"""The demo account: a merchant with sample customers, invoices, payments and a webhook endpoint.

The `demo` service runs this on every `docker compose up`, so the demo starts fresh each time.
Everything is created through the API itself, so the sample data obeys the same rules as real data:
balanced ledger entries, idempotent payments, and a webhook recorded with every payment. Only the
dates are moved back afterwards, so the invoices have a history.
"""
import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta

import httpx
from sqlalchemy import delete, select, update

from .db import SessionLocal, engine
from .models import Invoice, LedgerEntry, Payment, User, WebhookDelivery, WebhookEndpoint

# Not a secret: anyone running the stack can sign in to the demo, and the dashboard's demo button uses it.
DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo-account-not-secret"
RECEIVER_URL = "http://receiver:9000/hooks"

CUSTOMERS = {
    "riverside": ("Riverside Cafe", "accounts@riverside-cafe.example.com"),
    "ashby": ("Ashby Dental", "office@ashby-dental.example.com"),
    "kestrel": ("Kestrel Print", "studio@kestrel-print.example.com"),
    "harbour": ("Harbour Yoga", "hello@harbour-yoga.example.com"),
    "moorland": ("Moorland Books", "shop@moorland-books.example.com"),
}

# customer, currency, issued (days ago), lines (description, quantity, unit price in minor units),
# payments (amount in minor units, days after issue), voided (days after issue, or None)
INVOICES = [
    ("moorland", "GBP", 76, [("Stock export script", 1, 30000)], [], 5),
    ("ashby", "GBP", 65, [("Patient portal, phase 1", 1, 185000)], [(100000, 10), (85000, 28)], None),
    ("harbour", "GBP", 59, [("Booking page", 1, 42000)], [], None),
    ("kestrel", "EUR", 51, [("Brochure layout", 1, 96000)], [(96000, 20)], None),
    ("ashby", "GBP", 47, [("Website maintenance, Q3", 1, 27500)], [], None),
    ("riverside", "GBP", 12, [("Seasonal menu update", 1, 15000)], [], None),
    ("kestrel", "EUR", 8, [("Price list design", 2, 18000)], [], None),
    ("riverside", "GBP", 3, [("Menu photography, half day", 1, 30000), ("Image editing", 12, 1000)], [(20000, 0)], None),
]


def _ok(r: httpx.Response) -> dict:
    if r.status_code >= 400:
        raise RuntimeError(f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text}")
    return r.json()


async def seed(client: httpx.AsyncClient, today: date | None = None) -> None:
    today = today or datetime.now(UTC).date()
    now = datetime.now(UTC)

    # Start again: deleting the user removes everything it owns.
    async with SessionLocal() as session, session.begin():
        await session.execute(delete(User).where(User.email == DEMO_EMAIL))

    _ok(await client.post("/auth/register", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}))
    token = _ok(await client.post("/auth/token", data={"username": DEMO_EMAIL, "password": DEMO_PASSWORD}))["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    # The endpoint exists before any payment, so every payment records its webhooks.
    _ok(await client.post("/webhooks", json={"url": RECEIVER_URL}, headers=auth))
    customers = {key: _ok(await client.post("/customers", json={"name": n, "email": e}, headers=auth))["id"]
                 for key, (n, e) in CUSTOMERS.items()}

    # Each invoice, then the moments to move its records back to.
    moves: list[tuple[str, datetime, list[tuple[str, datetime]], datetime | None]] = []
    for customer, currency, issued_ago, lines, pays, voided in INVOICES:
        issued = now - timedelta(days=issued_ago, hours=3)
        inv = _ok(await client.post("/invoices", headers=auth, json={
            "customer_id": customers[customer], "currency": currency,
            "due_date": (today - timedelta(days=issued_ago) + timedelta(days=30)).isoformat(),
            "lines": [{"description": d, "quantity": q, "unit_price_minor": p} for d, q, p in lines]}))
        paid = []
        for amount, after in pays:
            p = _ok(await client.post(f"/invoices/{inv['id']}/payments", headers={**auth, "Idempotency-Key": str(uuid.uuid4())},
                                      json={"amount_minor": amount, "currency": currency}))
            paid.append((p["id"], issued + timedelta(days=after, hours=2)))
        if voided is not None:
            _ok(await client.post(f"/invoices/{inv['id']}/void", headers=auth))
        moves.append((inv["id"], issued, paid, issued + timedelta(days=voided, hours=1) if voided is not None else None))

    async with SessionLocal() as session, session.begin():
        for inv_id, issued, paid, voided_at in moves:
            inv_id = uuid.UUID(inv_id)
            await session.execute(update(Invoice).where(Invoice.id == inv_id).values(created_at=issued))
            await session.execute(update(LedgerEntry).where(LedgerEntry.invoice_id == inv_id, LedgerEntry.memo == "Invoice issued")
                                  .values(created_at=issued))
            if voided_at:
                await session.execute(update(LedgerEntry).where(LedgerEntry.invoice_id == inv_id, LedgerEntry.memo == "Invoice voided")
                                      .values(created_at=voided_at))
            for pay_id, at in paid:
                pay_id = uuid.UUID(pay_id)
                await session.execute(update(Payment).where(Payment.id == pay_id).values(created_at=at))
                await session.execute(update(LedgerEntry).where(LedgerEntry.payment_id == pay_id).values(created_at=at))
        # Each webhook event carries the time of the payment behind it: a payment.succeeded its own
        # payment, an invoice.paid the payment that settled the invoice.
        payment_at = {p: at for _, _, paid, _ in moves for p, at in paid}
        settled_at = {i: paid[-1][1] for i, _, paid, _ in moves if paid}
        deliveries = (await session.execute(select(WebhookDelivery).join(WebhookEndpoint)
                                            .join(User, User.id == WebhookEndpoint.owner_id)
                                            .where(User.email == DEMO_EMAIL))).scalars().all()
        for d in deliveries:
            data = d.payload.get("data", {})
            at = payment_at.get(data.get("payment_id")) or settled_at.get(data.get("invoice_id"))
            if at:
                d.created_at = at


async def main() -> None:
    from .main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://demo") as client:
        await seed(client)
    await engine.dispose()
    print(f"Demo account ready: {DEMO_EMAIL}, {len(INVOICES)} invoices")


if __name__ == "__main__":
    asyncio.run(main())
