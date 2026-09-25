"""Explicit, isolated live runner for V3 action and approval evaluation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import psycopg

from service_desk.evaluation.actions import ActionObservation
from service_desk.evaluation.models import ActionEvaluationCase, ActionEvaluationDataset
from service_desk.graph.orchestrator import ServiceDeskGraph
from service_desk.ticketing.actions import ActionService
from service_desk.ticketing.mcp import TicketGateway


logger = logging.getLogger(__name__)
PROPOSAL_TOOLS = frozenset(
    {
        "propose_create_ticket",
        "propose_update_ticket_status",
        "propose_update_ticket_priority",
    }
)


class LiveActionEvaluationSession:
    """Own isolated fixture setup/cleanup around one complete live dataset run."""

    def __init__(
        self,
        *,
        dataset: ActionEvaluationDataset,
        graph: ServiceDeskGraph,
        action_service: ActionService,
        ticket_gateway: TicketGateway,
        database_url: str,
    ) -> None:
        self._dataset = dataset
        self._graph = graph
        self._action_service = action_service
        self._ticket_gateway = ticket_gateway
        self._database_url = database_url
        self._fixture_ids: list[str] = []
        self._request_ids = [f"live-action-evaluation-{case.case_id}" for case in dataset.cases]

    def __enter__(self) -> "LiveActionEvaluationSession":
        self._prepare_fixtures()
        return self

    def __exit__(self, *_: object) -> None:
        self._cleanup()

    def observe(self, case: ActionEvaluationCase) -> ActionObservation:
        state = None
        action_id: str | None = None
        try:
            state = self._graph.invoke(
                case.customer_id,
                case.message,
                request_id=f"live-action-evaluation-{case.case_id}",
            )
            workflow_records = state["tool_calls"][1:]
            proposal_record = next(
                (record for record in workflow_records if record["name"] in PROPOSAL_TOOLS),
                None,
            )
            pending = state.get("pending_actions", [])
            action_id = pending[0]["action_id"] if pending else None
            before = self._receipt_count(action_id)
            action = None
            replay_safe: bool | None = None
            if case.decision == "approve" and action_id:
                action = self._action_service.approve(action_id, case.customer_id)
                if case.verify_approval_replay:
                    replay = self._action_service.approve(action_id, case.customer_id)
                    replay_safe = replay.status == "succeeded" and replay.result == action.result
            elif case.decision == "reject" and action_id:
                action = self._action_service.reject(action_id, case.customer_id)
                replay = self._action_service.approve(action_id, case.customer_id)
                replay_safe = replay.status == "rejected"

            after = self._receipt_count(action_id)
            ticket_fields: dict[str, object] = {}
            if action and action.result and isinstance(action.result.get("ticket"), dict):
                ticket_fields = dict(action.result["ticket"])
            elif case.setup_ticket:
                ticket = self._ticket_gateway.get_ticket(
                    case.setup_ticket.customer_id, case.setup_ticket.ticket_id
                )
                if ticket:
                    ticket_fields = ticket.model_dump(mode="json")
            audit = (
                tuple(
                    event.event_type
                    for event in self._action_service.audit(action_id, case.customer_id)
                )
                if action_id
                else ()
            )
            return ActionObservation(
                selected_route=state.get("selected_route"),
                needs_clarification=state.get("needs_clarification", False),
                write_intents=tuple(state.get("write_intents", [])),
                workflow_tool=proposal_record["name"] if proposal_record else None,
                workflow_status=proposal_record["status"] if proposal_record else None,
                action_status=action.status if action else (pending[0]["status"] if pending else None),
                mutation_count_before_decision=before,
                mutation_count_after_decision=after,
                ticket_fields=ticket_fields,
                knowledge_document_ids=tuple(
                    source["document_id"] for source in state.get("knowledge_sources", [])
                ),
                audit_event_types=audit,
                approval_replayed_safely=replay_safe,
                answer=state.get("answer"),
            )
        except Exception as error:
            logger.warning(
                "Live action evaluation case failed [case_id=%s, error_type=%s]",
                case.case_id,
                type(error).__name__,
            )
            return ActionObservation(
                selected_route=state.get("selected_route") if state else None,
                needs_clarification=state.get("needs_clarification", False) if state else False,
                write_intents=tuple(state.get("write_intents", [])) if state else (),
                workflow_tool=None,
                workflow_status=None,
                action_status=None,
                mutation_count_before_decision=self._receipt_count(action_id),
                mutation_count_after_decision=self._receipt_count(action_id),
                ticket_fields={},
                knowledge_document_ids=(),
                audit_event_types=(),
                approval_replayed_safely=None,
                error=type(error).__name__,
            )

    def _prepare_fixtures(self) -> None:
        fixtures = [case.setup_ticket for case in self._dataset.cases if case.setup_ticket]
        connection = psycopg.connect(self._database_url, autocommit=True)
        try:
            existing_action = connection.execute(
                "SELECT action_id FROM ticket_actions WHERE proposed_by_request_id = ANY(%s) LIMIT 1",
                (self._request_ids,),
            ).fetchone()
            if existing_action:
                raise RuntimeError(
                    "isolated evaluation action state already exists; use a fresh database or "
                    "explicitly inspect and clean the prior incomplete run"
                )
            for fixture in fixtures:
                assert fixture is not None
                exists = connection.execute(
                    "SELECT 1 FROM tickets WHERE ticket_id=%s", (fixture.ticket_id,)
                ).fetchone()
                if exists:
                    raise RuntimeError(
                        f"isolated evaluation fixture already exists: {fixture.ticket_id}"
                    )
            with connection.transaction():
                for fixture in fixtures:
                    assert fixture is not None
                    connection.execute(
                        """
                        INSERT INTO tickets (
                            ticket_id, customer_id, subject, category, status, priority,
                            created_at, updated_at
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            fixture.ticket_id,
                            fixture.customer_id,
                            fixture.subject,
                            fixture.category,
                            fixture.status,
                            fixture.priority,
                            datetime.now(UTC),
                            datetime.now(UTC),
                        ),
                    )
                    self._fixture_ids.append(fixture.ticket_id)
        finally:
            connection.close()

    def _receipt_count(self, action_id: str | None) -> int:
        if action_id is None:
            return 0
        connection = psycopg.connect(self._database_url, autocommit=True)
        try:
            return int(
                connection.execute(
                    "SELECT count(*) FROM ticket_action_receipts WHERE action_id=%s",
                    (action_id,),
                ).fetchone()[0]
            )
        finally:
            connection.close()

    def _cleanup(self) -> None:
        connection = psycopg.connect(self._database_url, autocommit=True)
        try:
            action_ids = [
                row[0]
                for row in connection.execute(
                    "SELECT action_id FROM ticket_actions WHERE proposed_by_request_id = ANY(%s)",
                    (self._request_ids,),
                ).fetchall()
            ]
            created_ticket_ids: list[str] = []
            if action_ids:
                created_ticket_ids = [
                    row[0]
                    for row in connection.execute(
                        """
                        SELECT result->'ticket'->>'id' FROM ticket_action_receipts
                        WHERE action_id = ANY(%s) AND result->'ticket'->>'id' IS NOT NULL
                        """,
                        (action_ids,),
                    ).fetchall()
                ]
                connection.execute(
                    "DELETE FROM ticket_action_audit_events WHERE action_id = ANY(%s)",
                    (action_ids,),
                )
                connection.execute(
                    "DELETE FROM ticket_action_receipts WHERE action_id = ANY(%s)", (action_ids,)
                )
                connection.execute(
                    "DELETE FROM ticket_actions WHERE action_id = ANY(%s)", (action_ids,)
                )
            ticket_ids = list(dict.fromkeys([*created_ticket_ids, *self._fixture_ids]))
            if ticket_ids:
                connection.execute("DELETE FROM tickets WHERE ticket_id = ANY(%s)", (ticket_ids,))
        finally:
            connection.close()
