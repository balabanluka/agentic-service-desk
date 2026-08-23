"""Explicit read-only tool functions over synthetic local data."""

from service_desk.data.repository import BusinessRepository
from service_desk.domain.models import Customer, Invoice, Subscription, Ticket


class BusinessTools:
    """The complete V1 business-tool surface. No method mutates data."""

    def __init__(self, repository: BusinessRepository) -> None:
        self._repository = repository

    def get_customer(self, customer_id: str) -> Customer | None:
        return self._repository.get_customer(customer_id)

    def get_subscription(self, customer_id: str) -> Subscription | None:
        return self._repository.get_subscription(customer_id)

    def get_invoice(self, invoice_id: str) -> Invoice | None:
        return self._repository.get_invoice(invoice_id)

    def list_tickets(self, customer_id: str) -> tuple[Ticket, ...]:
        return self._repository.list_tickets(customer_id)
