from __future__ import annotations

from datetime import UTC, datetime, timedelta

from service_desk.ai.gateway import RouteDecision, ToolCall, WorkflowRequest, WorkflowTurn
from service_desk.data.repository import BusinessRepository
from service_desk.graph.orchestrator import ServiceDeskGraph
from service_desk.graph.workflows.permissions import (
    ACTION_PROPOSAL_TOOLS,
    TOOL_POLICIES,
    ScopedToolExecutor,
)
from service_desk.ticketing.models import TicketAction
from service_desk.tools.business import BusinessTools
from tests.fakes import FakeModelGateway


class FakeActionService:
    def __init__(self) -> None:
        self.proposals: list[dict[str, object]] = []

    def propose(self, **values: object) -> TicketAction:
        self.proposals.append(values)
        now = datetime.now(UTC)
        return TicketAction(
            action_id="act_" + "b" * 32,
            customer_id=str(values["customer_id"]),
            route=str(values["route"]),
            action_type=str(values["action_type"]),
            payload=dict(values["payload"]),
            status="pending",
            proposed_by_request_id=str(values["request_id"]),
            expires_at=now + timedelta(minutes=30),
            created_at=now,
            updated_at=now,
        )


class CreateTicketGateway(FakeModelGateway):
    def route(self, message: str) -> RouteDecision:
        del message
        return RouteDecision(
            route="technical",
            needs_clarification=False,
            rationale="Explicit technical ticket creation request.",
            write_intents=("create_ticket",),
        )

    def next_workflow_turn(self, request: WorkflowRequest) -> WorkflowTurn:
        self.requests.append(request)
        if not request.tool_results:
            return WorkflowTurn(
                tool_calls=(
                    ToolCall(
                        name="propose_create_ticket",
                        arguments={"subject": "CSV export fails repeatedly", "priority": "high"},
                    ),
                )
            )
        return WorkflowTurn(answer="The ticket action is pending and requires approval.")


def test_graph_creates_only_a_pending_action_before_human_approval() -> None:
    actions = FakeActionService()
    gateway = CreateTicketGateway(route="technical")
    graph = ServiceDeskGraph(
        BusinessTools(BusinessRepository.from_default_seed()),
        gateway,
        action_service=actions,  # type: ignore[arg-type]
    )

    result = graph.invoke(
        "cus_orbit_001", "Please create a high-priority ticket for our CSV export failure."
    )

    assert len(actions.proposals) == 1
    assert actions.proposals[0]["payload"] == {
        "subject": "CSV export fails repeatedly",
        "priority": "high",
        "category": "technical",
    }
    assert result["tool_calls"][-1] == {
        "name": "propose_create_ticket",
        "status": "pending_approval",
    }
    assert result["pending_actions"][0]["approval_required"] is True
    assert result["pending_actions"][0]["status"] == "pending"


def test_action_tools_are_explicitly_classified_and_scoped() -> None:
    actions = FakeActionService()
    executor = ScopedToolExecutor(
        BusinessTools(BusinessRepository.from_default_seed()),
        "cus_orbit_001",
        "support",
        action_service=actions,  # type: ignore[arg-type]
        request_id="request-1",
        write_intents=("create_ticket", "update_ticket_status", "update_ticket_priority"),
    )

    assert set(ACTION_PROPOSAL_TOOLS).issubset(executor.allowed_names)
    for name in ACTION_PROPOSAL_TOOLS:
        assert TOOL_POLICIES[name].effect == "write_proposal"
        assert TOOL_POLICIES[name].approval_required is True


def test_answer_only_synthesis_never_receives_action_tools() -> None:
    class ExhaustBudgetGateway(FakeModelGateway):
        def next_workflow_turn(self, request: WorkflowRequest) -> WorkflowTurn:
            self.requests.append(request)
            if len(self.requests) <= 3:
                return WorkflowTurn(tool_calls=(ToolCall(name="get_customer"),))
            return WorkflowTurn(answer="No additional tool can run during synthesis.")

    actions = FakeActionService()
    gateway = ExhaustBudgetGateway(route="support")
    ServiceDeskGraph(
        BusinessTools(BusinessRepository.from_default_seed()),
        gateway,
        action_service=actions,  # type: ignore[arg-type]
    ).invoke("cus_orbit_001", "Tell me about my account")

    assert gateway.requests[-1].tools == ()


def test_informational_request_has_no_action_tool_surface() -> None:
    actions = FakeActionService()
    executor = ScopedToolExecutor(
        BusinessTools(BusinessRepository.from_default_seed()),
        "cus_orbit_001",
        "support",
        action_service=actions,  # type: ignore[arg-type]
        request_id="request-info",
        write_intents=(),
    )

    assert not set(ACTION_PROPOSAL_TOOLS).intersection(executor.allowed_names)


def test_structured_intent_exposes_only_the_matching_proposal_tool() -> None:
    executor = ScopedToolExecutor(
        BusinessTools(BusinessRepository.from_default_seed()),
        "cus_orbit_001",
        "support",
        action_service=FakeActionService(),  # type: ignore[arg-type]
        request_id="request-status",
        write_intents=("update_ticket_status",),
    )

    exposed = set(ACTION_PROPOSAL_TOOLS).intersection(executor.allowed_names)
    assert exposed == {"propose_update_ticket_status"}


def test_clarification_with_detected_write_intent_never_enters_a_workflow() -> None:
    class ClarificationWithIntentGateway(FakeModelGateway):
        def route(self, message: str) -> RouteDecision:
            del message
            return RouteDecision(
                needs_clarification=True,
                rationale="The request has independent technical and billing outcomes.",
                write_intents=("create_ticket",),
            )

    actions = FakeActionService()
    result = ServiceDeskGraph(
        BusinessTools(BusinessRepository.from_default_seed()),
        ClarificationWithIntentGateway(),
        action_service=actions,  # type: ignore[arg-type]
    ).invoke(
        "cus_orbit_001",
        "Open a webhook ticket and arrange an unrelated renewal credit.",
    )

    assert result["selected_route"] == "clarification"
    assert result["write_intents"] == ["create_ticket"]
    assert result["transitions"] == ["load_customer", "route_request", "clarify"]
    assert actions.proposals == []
