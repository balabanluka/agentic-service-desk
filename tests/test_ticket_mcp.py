from __future__ import annotations

from datetime import date

import anyio
from mcp import Client

from service_desk.domain.models import Ticket
from service_desk.ticketing.mcp import (
    McpTicketGateway,
    READ_POLICY,
    WRITE_POLICY,
    create_ticket_mcp_server,
)
from service_desk.ticketing.models import ActionType, TicketMutationResult


class FakeTicketBackend:
    def __init__(self) -> None:
        self.ticket = Ticket(
            id="tic_orbit_9001",
            customer_id="cus_orbit_001",
            subject="Synthetic MCP test ticket",
            category="support",
            status="open",
            priority="normal",
            updated_on=date(2026, 9, 14),
        )
        self.executions: list[tuple[str, ActionType]] = []

    def list_tickets(self, customer_id: str) -> tuple[Ticket, ...]:
        return (self.ticket,) if customer_id == self.ticket.customer_id else ()

    def get_ticket(self, customer_id: str, ticket_id: str) -> Ticket | None:
        if customer_id == self.ticket.customer_id and ticket_id == self.ticket.id:
            return self.ticket
        return None

    def execute_action(
        self, action_id: str, expected_type: ActionType
    ) -> TicketMutationResult:
        self.executions.append((action_id, expected_type))
        return TicketMutationResult(
            action_id=action_id,
            action_type=expected_type,
            ticket=self.ticket,
        )


def test_in_process_mcp_read_and_write_round_trip() -> None:
    backend = FakeTicketBackend()
    gateway = McpTicketGateway(create_ticket_mcp_server(backend))

    assert gateway.list_tickets("cus_orbit_001") == (backend.ticket,)
    assert gateway.get_ticket("cus_other_999", backend.ticket.id) is None
    result = gateway.execute("act_" + "a" * 32, "update_ticket_status")

    assert result.ticket == backend.ticket
    assert backend.executions == [("act_" + "a" * 32, "update_ticket_status")]


def test_mcp_tools_publish_explicit_read_write_and_approval_metadata() -> None:
    server = create_ticket_mcp_server(FakeTicketBackend())

    async def inspect_tools():
        async with Client(server, raise_exceptions=True) as client:
            return {tool.name: tool for tool in (await client.list_tools()).tools}

    tools = anyio.run(inspect_tools)

    assert tools["tickets_list"].meta["service_desk"] == READ_POLICY
    assert tools["tickets_list"].annotations.read_only_hint is True
    for name in ("ticket_create", "ticket_update_status", "ticket_update_priority"):
        assert tools[name].meta["service_desk"] == WRITE_POLICY
        assert tools[name].annotations.read_only_hint is False
        assert tools[name].annotations.idempotent_hint is True
