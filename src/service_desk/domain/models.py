"""Typed synthetic business entities used by V1."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Customer(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^cus_[a-z]+_\d{3}$")
    name: str
    company: str
    email: str


class Subscription(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^sub_[a-z]+_\d{3}$")
    customer_id: str
    plan: str
    status: str
    seats: int = Field(gt=0)
    renewal_date: date
    invoice_ids: tuple[str, ...] = ()


class Invoice(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^inv_[a-z]+_\d{4}$")
    customer_id: str
    subscription_id: str
    amount_cents: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    status: str
    issued_on: date
    due_on: date


class Ticket(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^tic_[a-z]+_\d{4}$")
    customer_id: str
    subject: str
    category: str
    status: str
    priority: str
    updated_on: date


class SeedData(BaseModel):
    """Validated fixture data with referential-integrity checks."""

    model_config = ConfigDict(frozen=True)

    customers: tuple[Customer, ...]
    subscriptions: tuple[Subscription, ...]
    invoices: tuple[Invoice, ...]
    tickets: tuple[Ticket, ...]

    @model_validator(mode="after")
    def has_consistent_references(self) -> "SeedData":
        customer_ids = {customer.id for customer in self.customers}
        subscription_ids = {subscription.id for subscription in self.subscriptions}
        invoice_ids = {invoice.id for invoice in self.invoices}

        if len(customer_ids) != len(self.customers):
            raise ValueError("customer IDs must be unique")
        if len(subscription_ids) != len(self.subscriptions):
            raise ValueError("subscription IDs must be unique")
        if len(invoice_ids) != len(self.invoices):
            raise ValueError("invoice IDs must be unique")

        for subscription in self.subscriptions:
            if subscription.customer_id not in customer_ids:
                raise ValueError(f"unknown customer: {subscription.customer_id}")
            if not set(subscription.invoice_ids).issubset(invoice_ids):
                raise ValueError(f"unknown invoice in subscription: {subscription.id}")

        for invoice in self.invoices:
            if invoice.customer_id not in customer_ids:
                raise ValueError(f"unknown customer: {invoice.customer_id}")
            if invoice.subscription_id not in subscription_ids:
                raise ValueError(f"unknown subscription: {invoice.subscription_id}")

        for ticket in self.tickets:
            if ticket.customer_id not in customer_ids:
                raise ValueError(f"unknown customer: {ticket.customer_id}")

        return self
