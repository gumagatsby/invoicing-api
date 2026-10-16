import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (BigInteger, CheckConstraint, Date, DateTime, Enum, ForeignKey, Integer, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def uid() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Role(str, enum.Enum):
    admin = "admin"
    merchant = "merchant"


class InvoiceStatus(str, enum.Enum):
    open = "open"
    paid = "paid"
    void = "void"


class Currency(str, enum.Enum):
    GBP = "GBP"
    USD = "USD"
    EUR = "EUR"


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = uid()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(Enum(Role, name="role"), default=Role.merchant, nullable=False)
    created_at: Mapped[datetime] = created()


class RefreshToken(Base):
    """One row per issued refresh token, so a token can be used once and then is dead."""
    __tablename__ = "refresh_tokens"
    id: Mapped[uuid.UUID] = uid()  # the token's jti
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    family: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[uuid.UUID] = uid()
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = created()


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint("paid_minor >= 0 AND paid_minor <= total_minor", name="paid_within_total"),
        CheckConstraint("total_minor > 0", name="total_positive"),
    )
    id: Mapped[uuid.UUID] = uid()
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    currency: Mapped[Currency] = mapped_column(Enum(Currency, name="currency"))
    status: Mapped[InvoiceStatus] = mapped_column(Enum(InvoiceStatus, name="invoice_status"), default=InvoiceStatus.open)
    due_date: Mapped[date] = mapped_column(Date)
    total_minor: Mapped[int] = mapped_column(BigInteger)
    paid_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = created()
    lines: Mapped[list["InvoiceLine"]] = relationship(cascade="all, delete-orphan", lazy="selectin", order_by="InvoiceLine.position")


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"
    id: Mapped[uuid.UUID] = uid()
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(500))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_minor: Mapped[int] = mapped_column(BigInteger)


class Payment(Base):
    __tablename__ = "payments"
    # The database itself refuses a second payment with the same key, whatever the application does.
    __table_args__ = (UniqueConstraint("owner_id", "idempotency_key", name="uq_payment_idempotency"),
                      CheckConstraint("amount_minor > 0", name="amount_positive"))
    id: Mapped[uuid.UUID] = uid()
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"), index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[Currency] = mapped_column(Enum(Currency, name="currency"))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = created()


class LedgerEntry(Base):
    """Double entry: every event writes equal debits and credits."""
    __tablename__ = "ledger_entries"
    __table_args__ = (CheckConstraint("(debit_minor = 0) <> (credit_minor = 0)", name="one_side_only"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"), index=True)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payments.id"))
    account: Mapped[str] = mapped_column(String(32))  # receivables | revenue | cash
    debit_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    credit_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    currency: Mapped[Currency] = mapped_column(Enum(Currency, name="currency"))
    memo: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = created()


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"
    id: Mapped[uuid.UUID] = uid()
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(Text)
    secret: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = created()


class WebhookDelivery(Base):
    """Written in the same transaction as the event (an outbox), so an event is never lost."""
    __tablename__ = "webhook_deliveries"
    id: Mapped[uuid.UUID] = uid()
    endpoint_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), index=True)
    event: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending | delivered | failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = created()
