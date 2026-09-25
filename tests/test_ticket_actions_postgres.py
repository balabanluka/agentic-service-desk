from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest

from service_desk.config import Settings
from service_desk.ticketing.actions import (
    ActionExecutionUnavailable,
    ActionProposalError,
    ActionService,
)
from service_desk.ticketing.mcp import (
    McpTicketGateway,
    PostgresTicketMcpBackend,
    TicketMcpUnavailable,
    create_ticket_mcp_server,
)


def _postgres_url() -> str:
    if os.getenv("RUN_POSTGRES_TESTS") != "1":
        pytest.skip("set RUN_POSTGRES_TESTS=1 to run local PostgreSQL integration tests")
    settings = Settings()
    if settings.database_url is None:
        pytest.skip("DATABASE_URL is not configured")
    return settings.database_url.get_secret_value()


@pytest.mark.postgres
@pytest.mark.mcp
def test_actions_are_durable_scoped_and_exactly_once_through_real_mcp() -> None:
    database_url = _postgres_url()
    run_id = uuid4().hex[:10]
    customer_id = f"cus_vthree_{run_id}"
    other_customer_id = f"cus_other_{run_id}"
    request_prefix = f"integration-{run_id}"
    gateway = McpTicketGateway(
        create_ticket_mcp_server(PostgresTicketMcpBackend(database_url))
    )
    service = ActionService(database_url=database_url, ticket_gateway=gateway)

    connection = psycopg.connect(database_url, autocommit=True)
    try:
        create = service.propose(
            customer_id=customer_id,
            route="technical",
            action_type="create_ticket",
            payload={
                "subject": "Isolated V3 concurrent approval ticket",
                "category": "technical",
                "priority": "high",
            },
            request_id=f"{request_prefix}-create",
        )
        assert create.status == "pending"
        assert gateway.list_tickets(customer_id) == ()

        with ThreadPoolExecutor(max_workers=2) as pool:
            completed = list(
                pool.map(lambda _: service.approve(create.action_id, customer_id), range(2))
            )

        assert {action.status for action in completed} == {"succeeded"}
        tickets = gateway.list_tickets(customer_id)
        assert len(tickets) == 1
        created_ticket = tickets[0]
        receipt_count = connection.execute(
            "SELECT count(*) FROM ticket_action_receipts WHERE action_id=%s",
            (create.action_id,),
        ).fetchone()[0]
        assert receipt_count == 1

        persisted = ActionService(database_url=database_url, ticket_gateway=gateway).get(
            create.action_id, customer_id
        )
        assert persisted.status == "succeeded"

        priority = service.propose(
            customer_id=customer_id,
            route="technical",
            action_type="update_ticket_priority",
            payload={"ticket_id": created_ticket.id, "priority": "critical"},
            request_id=f"{request_prefix}-priority",
        )
        assert gateway.get_ticket(customer_id, created_ticket.id).priority == "high"
        assert service.approve(priority.action_id, customer_id).status == "succeeded"
        assert service.approve(priority.action_id, customer_id).status == "succeeded"
        assert gateway.get_ticket(customer_id, created_ticket.id).priority == "critical"

        rejected = service.propose(
            customer_id=customer_id,
            route="technical",
            action_type="update_ticket_status",
            payload={"ticket_id": created_ticket.id, "status": "resolved"},
            request_id=f"{request_prefix}-reject",
        )
        assert service.reject(rejected.action_id, customer_id).status == "rejected"
        assert service.approve(rejected.action_id, customer_id).status == "rejected"
        assert gateway.get_ticket(customer_id, created_ticket.id).status == "open"

        with pytest.raises(ActionProposalError, match="ticket_not_available"):
            service.propose(
                customer_id=other_customer_id,
                route="technical",
                action_type="update_ticket_status",
                payload={"ticket_id": created_ticket.id, "status": "resolved"},
                request_id=f"{request_prefix}-cross-customer",
            )

        expired = service.propose(
            customer_id=customer_id,
            route="technical",
            action_type="create_ticket",
            payload={
                "subject": "This expired action must never create a ticket",
                "category": "technical",
                "priority": "low",
            },
            request_id=f"{request_prefix}-expired",
        )
        connection.execute(
            "UPDATE ticket_actions SET expires_at=%s WHERE action_id=%s",
            (datetime(2020, 1, 1, tzinfo=UTC), expired.action_id),
        )
        assert service.get(expired.action_id, customer_id).status == "expired"
        assert service.approve(expired.action_id, customer_id).status == "expired"
        assert len(gateway.list_tickets(customer_id)) == 1

        event_types = [event.event_type for event in service.audit(create.action_id, customer_id)]
        assert event_types == [
            "proposed",
            "approved",
            "execution_started",
            "mutation_committed",
            "succeeded",
        ]
    finally:
        action_ids = [
            row[0]
            for row in connection.execute(
                "SELECT action_id FROM ticket_actions WHERE proposed_by_request_id LIKE %s",
                (f"{request_prefix}%",),
            ).fetchall()
        ]
        if action_ids:
            connection.execute(
                "DELETE FROM ticket_action_audit_events WHERE action_id = ANY(%s)", (action_ids,)
            )
            connection.execute(
                "DELETE FROM ticket_action_receipts WHERE action_id = ANY(%s)", (action_ids,)
            )
            connection.execute("DELETE FROM ticket_actions WHERE action_id = ANY(%s)", (action_ids,))
        connection.execute("DELETE FROM tickets WHERE customer_id=%s", (customer_id,))
        connection.close()


@pytest.mark.postgres
def test_ambiguous_mcp_failure_stays_retryable_without_a_second_mutation() -> None:
    database_url = _postgres_url()
    run_id = uuid4().hex[:10]
    customer_id = f"cus_retry_{run_id}"
    request_id = f"integration-retry-{run_id}"
    real_gateway = McpTicketGateway(
        create_ticket_mcp_server(PostgresTicketMcpBackend(database_url))
    )

    class UnavailableGateway:
        def list_tickets(self, customer_id: str):
            return real_gateway.list_tickets(customer_id)

        def get_ticket(self, customer_id: str, ticket_id: str):
            return real_gateway.get_ticket(customer_id, ticket_id)

        def execute(self, action_id: str, action_type: str):
            raise TicketMcpUnavailable("simulated timeout")

    unavailable = ActionService(database_url=database_url, ticket_gateway=UnavailableGateway())
    action = unavailable.propose(
        customer_id=customer_id,
        route="support",
        action_type="create_ticket",
        payload={
            "subject": "Retry-safe MCP timeout check",
            "category": "support",
            "priority": "normal",
        },
        request_id=request_id,
    )
    try:
        with pytest.raises(ActionExecutionUnavailable):
            unavailable.approve(action.action_id, customer_id)
        assert unavailable.get(action.action_id, customer_id).status == "executing"

        recovered = ActionService(
            database_url=database_url, ticket_gateway=real_gateway
        ).approve(action.action_id, customer_id)
        assert recovered.status == "succeeded"
        assert len(real_gateway.list_tickets(customer_id)) == 1
    finally:
        connection = psycopg.connect(database_url, autocommit=True)
        connection.execute("DELETE FROM ticket_action_audit_events WHERE action_id=%s", (action.action_id,))
        connection.execute("DELETE FROM ticket_action_receipts WHERE action_id=%s", (action.action_id,))
        connection.execute("DELETE FROM ticket_actions WHERE action_id=%s", (action.action_id,))
        connection.execute("DELETE FROM tickets WHERE customer_id=%s", (customer_id,))
        connection.close()
