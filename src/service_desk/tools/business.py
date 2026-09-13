"""Explicit read-only tool functions over synthetic local data."""

from service_desk.data.repository import BusinessRepository
from service_desk.domain.models import Customer, Invoice, Subscription, Ticket
from service_desk.ticketing.mcp import TicketGateway


class BusinessTools:
    """The complete V1 business-tool surface. No method mutates data."""

    def __init__(
        self, repository: BusinessRepository, ticket_gateway: TicketGateway | None = None
    ) -> None:
        self._repository = repository
        self._ticket_gateway = ticket_gateway

    def get_customer(self, customer_id: str) -> Customer | None:
        return self._repository.get_customer(customer_id)

    def get_subscription(self, customer_id: str) -> Subscription | None:
        return self._repository.get_subscription(customer_id)

    def get_invoice(self, invoice_id: str) -> Invoice | None:
        return self._repository.get_invoice(invoice_id)

    def list_tickets(self, customer_id: str) -> tuple[Ticket, ...]:
        if self._ticket_gateway is not None:
            return self._ticket_gateway.list_tickets(customer_id)
        return self._repository.list_tickets(customer_id)
