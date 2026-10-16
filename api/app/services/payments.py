"""Taking a payment: idempotent, safe under concurrency, and always balanced in the ledger."""
import hashlib
import json
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Invoice, InvoiceStatus, LedgerEntry, Payment
from ..schemas import PaymentIn
from . import webhooks


def request_hash(invoice_id: uuid.UUID, body: PaymentIn) -> str:
    raw = json.dumps({"invoice": str(invoice_id), **body.model_dump(mode="json")}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


async def pay(session: AsyncSession, owner_id: uuid.UUID, invoice_id: uuid.UUID, body: PaymentIn,
              idempotency_key: str) -> tuple[Payment, bool]:
    """Returns (payment, created). A replay with the same key and body returns the original payment."""
    digest = request_hash(invoice_id, body)
    async with session.begin():
        # Lock the invoice row. Concurrent payments for the same invoice queue here, so they cannot
        # both read the same outstanding balance and overpay it.
        invoice = (await session.execute(
            select(Invoice).where(Invoice.id == invoice_id, Invoice.owner_id == owner_id).with_for_update()
        )).scalar_one_or_none()
        if invoice is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")

        existing = (await session.execute(
            select(Payment).where(Payment.owner_id == owner_id, Payment.idempotency_key == idempotency_key)
        )).scalar_one_or_none()
        if existing is not None:
            if existing.request_hash != digest:
                raise HTTPException(status.HTTP_409_CONFLICT, "Idempotency key already used with a different request")
            return existing, False

        if body.currency != invoice.currency:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Invoice is in {invoice.currency.value}")
        if invoice.status != InvoiceStatus.open:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Invoice is {invoice.status.value}")
        outstanding = invoice.total_minor - invoice.paid_minor
        if body.amount_minor > outstanding:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                f"Amount exceeds the outstanding balance of {outstanding}")

        payment = Payment(owner_id=owner_id, invoice_id=invoice.id, amount_minor=body.amount_minor,
                          currency=body.currency, idempotency_key=idempotency_key, request_hash=digest)
        session.add(payment)
        await session.flush()
        # Cash comes in; the customer owes less.
        session.add_all([
            LedgerEntry(owner_id=owner_id, invoice_id=invoice.id, payment_id=payment.id, account="cash",
                        debit_minor=body.amount_minor, credit_minor=0, currency=body.currency, memo="Payment received"),
            LedgerEntry(owner_id=owner_id, invoice_id=invoice.id, payment_id=payment.id, account="receivables",
                        debit_minor=0, credit_minor=body.amount_minor, currency=body.currency, memo="Payment received"),
        ])
        invoice.paid_minor += body.amount_minor
        if invoice.paid_minor == invoice.total_minor:
            invoice.status = InvoiceStatus.paid
            await webhooks.record(session, owner_id, "invoice.paid", {
                "invoice_id": str(invoice.id), "total_minor": invoice.total_minor, "currency": invoice.currency.value})
        await webhooks.record(session, owner_id, "payment.succeeded", {
            "payment_id": str(payment.id), "invoice_id": str(invoice.id), "amount_minor": payment.amount_minor,
            "currency": payment.currency.value})
    return payment, True
