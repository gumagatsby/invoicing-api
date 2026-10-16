import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl

from .models import Currency, InvoiceStatus, Role


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Register(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class Tokens(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class Refresh(BaseModel):
    refresh_token: str


class UserOut(ORM):
    id: uuid.UUID
    email: EmailStr
    role: Role


class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr


class CustomerOut(ORM):
    id: uuid.UUID
    name: str
    email: str
    created_at: datetime


class LineIn(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    quantity: int = Field(ge=1, le=100_000)
    unit_price_minor: int = Field(ge=1, le=10_000_000_00)


class InvoiceIn(BaseModel):
    customer_id: uuid.UUID
    currency: Currency
    due_date: date
    lines: list[LineIn] = Field(min_length=1, max_length=100)


class LineOut(ORM):
    description: str
    quantity: int
    unit_price_minor: int


class InvoiceOut(ORM):
    id: uuid.UUID
    customer_id: uuid.UUID
    currency: Currency
    status: InvoiceStatus
    due_date: date
    total_minor: int
    paid_minor: int
    outstanding_minor: int
    created_at: datetime
    lines: list[LineOut]


class PaymentIn(BaseModel):
    amount_minor: int = Field(ge=1)
    currency: Currency


class PaymentOut(ORM):
    id: uuid.UUID
    invoice_id: uuid.UUID
    amount_minor: int
    currency: Currency
    created_at: datetime


class LedgerOut(ORM):
    account: str
    debit_minor: int
    credit_minor: int
    currency: Currency
    memo: str
    created_at: datetime


class WebhookIn(BaseModel):
    url: HttpUrl


class WebhookOut(ORM):
    id: uuid.UUID
    url: str
    active: bool
    secret: str | None = None  # shown once, at creation


class DeliveryOut(ORM):
    id: uuid.UUID
    event: str
    status: str
    attempts: int
    last_status_code: int | None
    created_at: datetime


