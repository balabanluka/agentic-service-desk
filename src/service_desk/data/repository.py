"""In-memory indexes over the version-controlled synthetic data set."""

import json
from pathlib import Path

from service_desk.domain.models import Customer, Invoice, SeedData, Subscription, Ticket


class BusinessRepository:
    def __init__(self, seed_data: SeedData) -> None:
        self._customers = {customer.id: customer for customer in seed_data.customers}
        self._subscriptions = {
            subscription.customer_id: subscription for subscription in seed_data.subscriptions
        }
        self._invoices = {invoice.id: invoice for invoice in seed_data.invoices}
        self._tickets = {
            customer_id: tuple(
                ticket for ticket in seed_data.tickets if ticket.customer_id == customer_id
            )
            for customer_id in self._customers
        }

    @classmethod
    def from_json_file(cls, path: Path) -> "BusinessRepository":
        raw_data = json.loads(path.read_text(encoding="utf-8"))
        return cls(SeedData.model_validate(raw_data))

    @classmethod
    def from_default_seed(cls) -> "BusinessRepository":
        return cls.from_json_file(Path(__file__).with_name("seed.json"))

    def get_customer(self, customer_id: str) -> Customer | None:
        return self._customers.get(customer_id)

    def get_subscription(self, customer_id: str) -> Subscription | None:
        return self._subscriptions.get(customer_id)

    def get_invoice(self, invoice_id: str) -> Invoice | None:
        return self._invoices.get(invoice_id)

    def list_tickets(self, customer_id: str) -> tuple[Ticket, ...]:
        return self._tickets.get(customer_id, ())
