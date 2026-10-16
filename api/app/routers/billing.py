"""Customers, invoices, payments and the ledger. Every query is scoped to the caller's own records."""
import base64
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import rate_limited
from ..metrics import PAYMENTS
from ..models import Customer, Invoice, InvoiceLine, InvoiceStatus, LedgerEntry, Payment, User
from ..schemas import CustomerIn, CustomerOut, InvoiceIn, InvoiceOut, LedgerOut, PaymentIn, PaymentOut
from ..services import payments

router = APIRouter(tags=["billing"])


def _cursor(created_at: datetime, id_: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{created_at.isoformat()}|{id_}".encode()).decode()


def _uncursor(c: str) -> tuple[datetime, uuid.UUID]:
    try:
        ts, id_ = base64.urlsafe_b64decode(c.encode()).decode().split("|")
        return datetime.fromisoformat(ts), uuid.UUID(id_)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bad cursor")


def _invoice_out(inv: Invoice) -> InvoiceOut:
    return InvoiceOut.model_validate({**{c: getattr(inv, c) for c in
                                         ("id", "customer_id", "currency", "status", "due_date", "total_minor",
                                          "paid_minor", "created_at", "lines")},
                                      "outstanding_minor": inv.total_minor - inv.paid_minor})


# ---- customers

@router.post("/customers", response_model=CustomerOut, status_code=201)
async def create_customer(body: CustomerIn, user: User = Depends(rate_limited), session: AsyncSession = Depends(get_session)):
    c = Customer(owner_id=user.id, name=body.name, email=body.email)
    session.add(c)
    await session.commit()
    return c


@router.get("/customers", response_model=list[CustomerOut])
async def list_customers(user: User = Depends(rate_limited), session: AsyncSession = Depends(get_session)):
    return (await session.execute(select(Customer).where(Customer.owner_id == user.id)
                                  .order_by(Customer.created_at.desc()).limit(200))).scalars().all()


# ---- invoices

@router.post("/invoices", response_model=InvoiceOut, status_code=201)
async def create_invoice(body: InvoiceIn, user: User = Depends(rate_limited), session: AsyncSession = Depends(get_session)):
    async with session.begin():
        customer = await session.get(Customer, body.customer_id)
        if customer is None or customer.owner_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
        total = sum(l.quantity * l.unit_price_minor for l in body.lines)
        inv = Invoice(owner_id=user.id, customer_id=customer.id, currency=body.currency, due_date=body.due_date,
                      total_minor=total, paid_minor=0, status=InvoiceStatus.open,
                      lines=[InvoiceLine(position=i, **l.model_dump()) for i, l in enumerate(body.lines)])
        session.add(inv)
        await session.flush()
        # Issuing the invoice: the customer now owes us, and we have earned the revenue.
        session.add_all([
            LedgerEntry(owner_id=user.id, invoice_id=inv.id, account="receivables", debit_minor=total, credit_minor=0,
                        currency=body.currency, memo="Invoice issued"),
            LedgerEntry(owner_id=user.id, invoice_id=inv.id, account="revenue", debit_minor=0, credit_minor=total,
                        currency=body.currency, memo="Invoice issued"),
        ])
    return _invoice_out(inv)


@router.get("/invoices")
async def list_invoices(status_: InvoiceStatus | None = Query(None, alias="status"), limit: int = Query(20, ge=1, le=100),
                        cursor: str | None = None, user: User = Depends(rate_limited),
                        session: AsyncSession = Depends(get_session)):
    q = select(Invoice).where(Invoice.owner_id == user.id)
    if status_:
        q = q.where(Invoice.status == status_)
    if cursor:
        ts, id_ = _uncursor(cursor)
        q = q.where(tuple_(Invoice.created_at, Invoice.id) < tuple_(ts, id_))
    rows = (await session.execute(q.order_by(Invoice.created_at.desc(), Invoice.id.desc()).limit(limit + 1))).scalars().all()
    nxt = _cursor(rows[limit - 1].created_at, rows[limit - 1].id) if len(rows) > limit else None
    return {"items": [_invoice_out(r) for r in rows[:limit]], "next_cursor": nxt}


async def _own_invoice(session: AsyncSession, user: User, invoice_id: uuid.UUID) -> Invoice:
    inv = await session.get(Invoice, invoice_id)
    # 404, not 403: another merchant's invoice should be indistinguishable from one that does not exist.
    if inv is None or inv.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    return inv


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut)
async def get_invoice(invoice_id: uuid.UUID, user: User = Depends(rate_limited), session: AsyncSession = Depends(get_session)):
    return _invoice_out(await _own_invoice(session, user, invoice_id))


@router.post("/invoices/{invoice_id}/void", response_model=InvoiceOut)
async def void_invoice(invoice_id: uuid.UUID, user: User = Depends(rate_limited), session: AsyncSession = Depends(get_session)):
    async with session.begin():
        inv = (await session.execute(select(Invoice).where(Invoice.id == invoice_id, Invoice.owner_id == user.id)
                                     .with_for_update())).scalar_one_or_none()
        if inv is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
        if inv.status != InvoiceStatus.open or inv.paid_minor > 0:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Only an open, unpaid invoice can be voided")
        inv.status = InvoiceStatus.void
        # Reverse the issuing entries rather than deleting them: the ledger is append-only.
        session.add_all([
            LedgerEntry(owner_id=user.id, invoice_id=inv.id, account="revenue", debit_minor=inv.total_minor, credit_minor=0,
                        currency=inv.currency, memo="Invoice voided"),
            LedgerEntry(owner_id=user.id, invoice_id=inv.id, account="receivables", debit_minor=0, credit_minor=inv.total_minor,
                        currency=inv.currency, memo="Invoice voided"),
        ])
    return _invoice_out(inv)


# ---- payments

@router.post("/invoices/{invoice_id}/payments", response_model=PaymentOut, status_code=201)
async def create_payment(invoice_id: uuid.UUID, body: PaymentIn, response: Response,
                         idempotency_key: str = Header(..., min_length=8, max_length=255),
                         user: User = Depends(rate_limited), session: AsyncSession = Depends(get_session)):
    payment, created = await payments.pay(session, user.id, invoice_id, body, idempotency_key)
    PAYMENTS.labels(outcome="created" if created else "replayed").inc()
    if not created:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replayed"] = "true"
    return payment


@router.get("/invoices/{invoice_id}/payments", response_model=list[PaymentOut])
async def list_payments(invoice_id: uuid.UUID, user: User = Depends(rate_limited), session: AsyncSession = Depends(get_session)):
    await _own_invoice(session, user, invoice_id)
    return (await session.execute(select(Payment).where(Payment.invoice_id == invoice_id)
                                  .order_by(Payment.created_at))).scalars().all()


# ---- ledger

@router.get("/ledger", response_model=list[LedgerOut])
async def ledger(invoice_id: uuid.UUID | None = None, user: User = Depends(rate_limited),
                 session: AsyncSession = Depends(get_session)):
    q = select(LedgerEntry).where(LedgerEntry.owner_id == user.id)
    if invoice_id:
        q = q.where(LedgerEntry.invoice_id == invoice_id)
    return (await session.execute(q.order_by(LedgerEntry.id).limit(500))).scalars().all()


@router.get("/ledger/balances")
async def balances(user: User = Depends(rate_limited), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        select(LedgerEntry.currency, LedgerEntry.account, func.sum(LedgerEntry.debit_minor), func.sum(LedgerEntry.credit_minor))
        .where(LedgerEntry.owner_id == user.id).group_by(LedgerEntry.currency, LedgerEntry.account)
    )).all()
    out: dict = {}
    for cur, acct, dr, cr in rows:
        out.setdefault(cur.value, {})[acct] = {"debit_minor": int(dr), "credit_minor": int(cr), "balance_minor": int(dr - cr)}
    for cur, accts in out.items():
        accts["_balanced"] = sum(a["debit_minor"] for a in accts.values()) == sum(a["credit_minor"] for a in accts.values())
    return out
