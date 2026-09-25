"""Direct psycopg repositories for mutable tickets and approval actions."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any, Literal, Self

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from service_desk.ai.gateway import RouteName
from service_desk.domain.models import Ticket
from service_desk.ticketing.models import (
    ActionStatus,
    ActionType,
    AuditEvent,
    CreateTicketPayload,
    TicketAction,
    TicketMutationResult,
    UpdateTicketPriorityPayload,
    UpdateTicketStatusPayload,
    validate_action_payload,
)


ActorType = Literal["model", "human", "system", "mcp"]
TERMINAL_ACTION_STATUSES = frozenset({"succeeded", "failed", "rejected", "expired"})


class TicketActionNotExecutable(RuntimeError):
    """Raised when the canonical durable action cannot safely execute."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class TicketRepository:
    """Mutable ticket data and idempotent MCP execution primitives."""

    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    @classmethod
    def connect(cls, database_url: str) -> Self:
        return cls(psycopg.connect(database_url, autocommit=True))

    def close(self) -> None:
        self._connection.close()

    def seed(self, tickets: Sequence[Ticket]) -> int:
        inserted = 0
        with self._connection.transaction(), self._connection.cursor() as cursor:
            for ticket in tickets:
                updated_at = datetime.combine(ticket.updated_on, datetime.min.time(), tzinfo=UTC)
                cursor.execute(
                    """
                    INSERT INTO tickets (
                        ticket_id, customer_id, subject, category, status, priority,
                        created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ticket_id) DO NOTHING
                    """,
                    (
                        ticket.id,
                        ticket.customer_id,
                        ticket.subject,
                        ticket.category,
                        ticket.status,
                        ticket.priority,
                        updated_at,
                        updated_at,
                    ),
                )
                inserted += cursor.rowcount
        return inserted

    def list_tickets(self, customer_id: str) -> tuple[Ticket, ...]:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT ticket_id, customer_id, subject, category, status, priority, updated_at
                FROM tickets WHERE customer_id = %s
                ORDER BY updated_at DESC, ticket_id
                """,
                (customer_id,),
            )
            return tuple(_ticket_from_row(row) for row in cursor.fetchall())

    def get_ticket(self, customer_id: str, ticket_id: str) -> Ticket | None:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT ticket_id, customer_id, subject, category, status, priority, updated_at
                FROM tickets WHERE customer_id = %s AND ticket_id = %s
                """,
                (customer_id, ticket_id),
            )
            row = cursor.fetchone()
            return _ticket_from_row(row) if row else None

    def execute_action(self, action_id: str, expected_type: ActionType) -> TicketMutationResult:
        """Execute the canonical action once; a receipt makes every retry a replay."""

        with self._connection.transaction(), self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT * FROM ticket_actions WHERE action_id = %s FOR UPDATE",
                (action_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise TicketActionNotExecutable("action_not_found")

            cursor.execute(
                "SELECT action_type, result FROM ticket_action_receipts WHERE action_id = %s",
                (action_id,),
            )
            receipt = cursor.fetchone()
            if receipt is not None:
                if str(receipt["action_type"]) != expected_type:
                    raise TicketActionNotExecutable("action_type_mismatch")
                stored = TicketMutationResult.model_validate(receipt["result"])
                return stored.model_copy(update={"replayed": True})

            if str(row["action_type"]) != expected_type:
                raise TicketActionNotExecutable("action_type_mismatch")
            if str(row["status"]) not in {"approved", "executing"}:
                raise TicketActionNotExecutable("action_not_approved")
            if row["expires_at"] <= datetime.now(UTC):
                raise TicketActionNotExecutable("action_expired")

            action = _action_from_row(row)
            payload = validate_action_payload(action.action_type, action.payload)
            ticket = self._apply_mutation(cursor, action, payload)
            result = TicketMutationResult(
                action_id=action.action_id,
                action_type=action.action_type,
                ticket=ticket,
            )
            cursor.execute(
                """
                INSERT INTO ticket_action_receipts (action_id, action_type, result)
                VALUES (%s, %s, %s)
                """,
                (action.action_id, action.action_type, Jsonb(result.model_dump(mode="json"))),
            )
            cursor.execute(
                """
                INSERT INTO ticket_action_audit_events
                    (action_id, event_type, actor_type, metadata)
                VALUES (%s, 'mutation_committed', 'mcp', %s)
                """,
                (action.action_id, Jsonb({"ticket_id": ticket.id})),
            )
            return result

    def _apply_mutation(
        self,
        cursor: psycopg.Cursor[dict[str, Any]],
        action: TicketAction,
        payload: Any,
    ) -> Ticket:
        if isinstance(payload, CreateTicketPayload):
            ticket_id = f"tic_action_{action.action_id.removeprefix('act_')[:12]}"
            cursor.execute(
                """
                INSERT INTO tickets
                    (ticket_id, customer_id, subject, category, status, priority)
                VALUES (%s, %s, %s, %s, 'open', %s)
                RETURNING ticket_id, customer_id, subject, category, status, priority, updated_at
                """,
                (ticket_id, action.customer_id, payload.subject, payload.category, payload.priority),
            )
        elif isinstance(payload, UpdateTicketStatusPayload):
            cursor.execute(
                """
                UPDATE tickets SET status = %s, updated_at = now(), version = version + 1
                WHERE ticket_id = %s AND customer_id = %s AND category = %s
                RETURNING ticket_id, customer_id, subject, category, status, priority, updated_at
                """,
                (payload.status, payload.ticket_id, action.customer_id, action.route),
            )
        else:
            assert isinstance(payload, UpdateTicketPriorityPayload)
            cursor.execute(
                """
                UPDATE tickets SET priority = %s, updated_at = now(), version = version + 1
                WHERE ticket_id = %s AND customer_id = %s AND category = %s
                RETURNING ticket_id, customer_id, subject, category, status, priority, updated_at
                """,
                (payload.priority, payload.ticket_id, action.customer_id, action.route),
            )
        row = cursor.fetchone()
        if row is None:
            raise TicketActionNotExecutable("ticket_not_owned_or_wrong_domain")
        return _ticket_from_row(row)


class ActionRepository:
    """Durable action lifecycle with row locks and append-only audit events."""

    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    @classmethod
    def connect(cls, database_url: str) -> Self:
        return cls(psycopg.connect(database_url, autocommit=True))

    def close(self) -> None:
        self._connection.close()

    def create_pending(
        self,
        *,
        action_id: str,
        customer_id: str,
        route: RouteName,
        action_type: ActionType,
        payload: dict[str, object],
        proposed_by_request_id: str,
        proposal_key: str,
        expires_at: datetime,
    ) -> TicketAction:
        validate_action_payload(action_type, payload)
        with self._connection.transaction(), self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                INSERT INTO ticket_actions (
                    action_id, customer_id, route, action_type, payload, status,
                    proposed_by_request_id, proposal_key, expires_at
                ) VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s, %s)
                ON CONFLICT (proposal_key) DO NOTHING
                RETURNING *
                """,
                (
                    action_id,
                    customer_id,
                    route,
                    action_type,
                    Jsonb(payload),
                    proposed_by_request_id,
                    proposal_key,
                    expires_at,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute("SELECT * FROM ticket_actions WHERE proposal_key = %s", (proposal_key,))
                row = cursor.fetchone()
                assert row is not None
                return _action_from_row(row)
            cursor.execute(
                """
                INSERT INTO ticket_action_audit_events
                    (action_id, event_type, actor_type, metadata)
                VALUES (%s, 'proposed', 'model', %s)
                """,
                (action_id, Jsonb({"route": route, "action_type": action_type})),
            )
            return _action_from_row(row)

    def get_for_customer(self, action_id: str, customer_id: str) -> TicketAction | None:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT * FROM ticket_actions WHERE action_id = %s AND customer_id = %s",
                (action_id, customer_id),
            )
            row = cursor.fetchone()
            return _action_from_row(row) if row else None

    def expire_pending(self, action_id: str, customer_id: str) -> TicketAction | None:
        now = datetime.now(UTC)
        with self._connection.transaction(), self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT * FROM ticket_actions WHERE action_id=%s AND customer_id=%s FOR UPDATE",
                (action_id, customer_id),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            if str(row["status"]) == "pending" and row["expires_at"] <= now:
                cursor.execute(
                    "UPDATE ticket_actions SET status='expired', completed_at=%s, updated_at=%s WHERE action_id=%s RETURNING *",
                    (now, now, action_id),
                )
                row = cursor.fetchone()
                self._audit(cursor, action_id, "expired", "system", {})
            return _action_from_row(row)

    def begin_approval(self, action_id: str, customer_id: str) -> TicketAction | None:
        now = datetime.now(UTC)
        with self._connection.transaction(), self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT * FROM ticket_actions
                WHERE action_id = %s AND customer_id = %s FOR UPDATE
                """,
                (action_id, customer_id),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            status = str(row["status"])
            if status in TERMINAL_ACTION_STATUSES:
                return _action_from_row(row)
            if row["expires_at"] <= now and status == "pending":
                cursor.execute(
                    "UPDATE ticket_actions SET status='expired', completed_at=%s, updated_at=%s WHERE action_id=%s RETURNING *",
                    (now, now, action_id),
                )
                expired_row = cursor.fetchone()
                self._audit(cursor, action_id, "expired", "system", {})
                return _action_from_row(expired_row)
            if status == "pending":
                self._audit(cursor, action_id, "approved", "human", {})
            if status != "executing":
                self._audit(cursor, action_id, "execution_started", "system", {})
            cursor.execute(
                """
                UPDATE ticket_actions SET
                    status='executing', approved_at=COALESCE(approved_at, %s),
                    execution_started_at=COALESCE(execution_started_at, %s), updated_at=%s,
                    error_code=NULL
                WHERE action_id=%s RETURNING *
                """,
                (now, now, now, action_id),
            )
            executing_row = cursor.fetchone()
            return _action_from_row(executing_row)

    def reject(self, action_id: str, customer_id: str) -> TicketAction | None:
        now = datetime.now(UTC)
        with self._connection.transaction(), self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT * FROM ticket_actions WHERE action_id=%s AND customer_id=%s FOR UPDATE",
                (action_id, customer_id),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            if str(row["status"]) == "pending" and row["expires_at"] <= now:
                cursor.execute(
                    "UPDATE ticket_actions SET status='expired', completed_at=%s, updated_at=%s WHERE action_id=%s RETURNING *",
                    (now, now, action_id),
                )
                row = cursor.fetchone()
                self._audit(cursor, action_id, "expired", "system", {})
            elif str(row["status"]) == "pending":
                cursor.execute(
                    "UPDATE ticket_actions SET status='rejected', rejected_at=%s, completed_at=%s, updated_at=%s WHERE action_id=%s RETURNING *",
                    (now, now, now, action_id),
                )
                row = cursor.fetchone()
                self._audit(cursor, action_id, "rejected", "human", {})
            return _action_from_row(row)

    def mark_succeeded(self, action_id: str, result: TicketMutationResult) -> TicketAction:
        now = datetime.now(UTC)
        with self._connection.transaction(), self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT status FROM ticket_actions WHERE action_id=%s FOR UPDATE", (action_id,)
            )
            status = str(cursor.fetchone()["status"])
            if status != "succeeded":
                cursor.execute(
                    "UPDATE ticket_actions SET status='succeeded', result=%s, error_code=NULL, completed_at=%s, updated_at=%s WHERE action_id=%s RETURNING *",
                    (Jsonb(result.model_dump(mode="json")), now, now, action_id),
                )
                row = cursor.fetchone()
                self._audit(cursor, action_id, "succeeded", "system", {"ticket_id": result.ticket.id})
            else:
                cursor.execute("SELECT * FROM ticket_actions WHERE action_id=%s", (action_id,))
                row = cursor.fetchone()
            return _action_from_row(row)

    def mark_failed(self, action_id: str, error_code: str) -> TicketAction:
        now = datetime.now(UTC)
        with self._connection.transaction(), self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "UPDATE ticket_actions SET status='failed', error_code=%s, completed_at=%s, updated_at=%s WHERE action_id=%s AND status<>'succeeded' RETURNING *",
                (error_code, now, now, action_id),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute("SELECT * FROM ticket_actions WHERE action_id=%s", (action_id,))
                row = cursor.fetchone()
            self._audit(cursor, action_id, "failed", "system", {"error_code": error_code})
            return _action_from_row(row)

    def record_execution_deferred(self, action_id: str, error_code: str) -> None:
        with self._connection.transaction(), self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "UPDATE ticket_actions SET error_code=%s, updated_at=now() WHERE action_id=%s AND status='executing'",
                (error_code, action_id),
            )
            if cursor.rowcount:
                self._audit(cursor, action_id, "execution_deferred", "system", {"error_code": error_code})

    def audit_events(self, action_id: str, customer_id: str) -> tuple[AuditEvent, ...]:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT ae.* FROM ticket_action_audit_events ae
                JOIN ticket_actions a ON a.action_id=ae.action_id
                WHERE ae.action_id=%s AND a.customer_id=%s ORDER BY ae.event_id
                """,
                (action_id, customer_id),
            )
            return tuple(AuditEvent.model_validate(row) for row in cursor.fetchall())

    @staticmethod
    def _audit(
        cursor: psycopg.Cursor[dict[str, Any]],
        action_id: str,
        event_type: str,
        actor_type: ActorType,
        metadata: dict[str, object],
    ) -> None:
        cursor.execute(
            "INSERT INTO ticket_action_audit_events (action_id,event_type,actor_type,metadata) VALUES (%s,%s,%s,%s)",
            (action_id, event_type, actor_type, Jsonb(metadata)),
        )


def _ticket_from_row(row: dict[str, Any]) -> Ticket:
    updated_at = row["updated_at"]
    updated_on = updated_at.date() if isinstance(updated_at, datetime) else date.fromisoformat(str(updated_at))
    return Ticket(
        id=str(row["ticket_id"]),
        customer_id=str(row["customer_id"]),
        subject=str(row["subject"]),
        category=str(row["category"]),
        status=str(row["status"]),
        priority=str(row["priority"]),
        updated_on=updated_on,
    )


def _action_from_row(row: dict[str, Any]) -> TicketAction:
    return TicketAction(
        action_id=str(row["action_id"]),
        customer_id=str(row["customer_id"]),
        route=str(row["route"]),
        action_type=str(row["action_type"]),
        payload=dict(row["payload"]),
        status=str(row["status"]),
        approval_required=bool(row["approval_required"]),
        proposed_by_request_id=str(row["proposed_by_request_id"]),
        expires_at=row["expires_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        result=dict(row["result"]) if row["result"] is not None else None,
        error_code=str(row["error_code"]) if row["error_code"] else None,
    )
