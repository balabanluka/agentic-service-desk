import pytest

from service_desk.ai.gateway import ToolCall, WorkflowRequest, WorkflowTurn
from service_desk.data.repository import BusinessRepository
from service_desk.graph.orchestrator import ServiceDeskGraph, WorkflowBoundedError
from service_desk.graph.workflows.permissions import WORKFLOW_ALLOWLISTS
from service_desk.tools.business import BusinessTools
from tests.fakes import FakeModelGateway


@pytest.mark.parametrize("route,workflow", [("support", "support_workflow"), ("billing", "billing_workflow"), ("technical", "technical_workflow")])
def test_graph_reaches_selected_workflow_with_a_scoped_tool(route: str, workflow: str) -> None:
    gateway = FakeModelGateway(route=route)
    graph = ServiceDeskGraph(BusinessTools(BusinessRepository.from_default_seed()), gateway)

    result = graph.invoke("cus_orbit_001", "Please help")

    assert result["selected_route"] == route
    assert result["transitions"] == ["load_customer", "route_request", workflow]
    assert result["tool_calls"][-1]["name"] in {tool["name"] for tool in gateway.requests[0].tools}
    assert result["answer_source"] == "model"


def test_graph_uses_explicit_clarification_branch() -> None:
    graph = ServiceDeskGraph(
        BusinessTools(BusinessRepository.from_default_seed()), FakeModelGateway(clarification=True)
    )

    result = graph.invoke("cus_orbit_001", "Help with everything")

    assert result["selected_route"] == "clarification"
    assert result["transitions"] == ["load_customer", "route_request", "clarify"]


def test_graph_stops_before_model_for_unknown_customer() -> None:
    gateway = FakeModelGateway()
    graph = ServiceDeskGraph(BusinessTools(BusinessRepository.from_default_seed()), gateway)

    result = graph.invoke("cus_unknown_999", "Help me")

    assert result["error_code"] == "customer_not_found"
    assert result["transitions"] == ["load_customer", "customer_not_found"]
    assert gateway.requests == []


class DisallowedToolGateway(FakeModelGateway):
    def next_workflow_turn(self, request: WorkflowRequest) -> WorkflowTurn:
        self.requests.append(request)
        return WorkflowTurn(tool_calls=(ToolCall(name="get_invoice", arguments={"invoice_id": "inv_orbit_1001"}),))


def test_graph_rejects_a_tool_outside_the_selected_workflow_allowlist() -> None:
    graph = ServiceDeskGraph(
        BusinessTools(BusinessRepository.from_default_seed()), DisallowedToolGateway(route="technical")
    )

    with pytest.raises(Exception, match="outside the allowlist"):
        graph.invoke("cus_orbit_001", "The export is failing")


class ExcessiveToolCallsGateway(FakeModelGateway):
    def next_workflow_turn(self, request: WorkflowRequest) -> WorkflowTurn:
        self.requests.append(request)
        return WorkflowTurn(tool_calls=tuple(ToolCall(name="list_tickets") for _ in range(4)))


def test_graph_enforces_a_total_tool_call_budget() -> None:
    graph = ServiceDeskGraph(
        BusinessTools(BusinessRepository.from_default_seed()), ExcessiveToolCallsGateway(route="support")
    )

    with pytest.raises(Exception, match="tool_call_budget_exceeded"):
        graph.invoke("cus_orbit_001", "Please help")


class ThreeToolBillingGateway(FakeModelGateway):
    def __init__(self) -> None:
        super().__init__(route="billing")
        self._calls = (
            ToolCall(name="get_customer"),
            ToolCall(name="get_subscription"),
            ToolCall(name="get_invoice", arguments={"invoice_id": "inv_willow_2001"}),
        )

    def next_workflow_turn(self, request: WorkflowRequest) -> WorkflowTurn:
        self.requests.append(request)
        request_number = len(self.requests)
        if request_number <= len(self._calls):
            return WorkflowTurn(tool_calls=(self._calls[request_number - 1],))
        assert request.tools == ()
        assert request.tool_results[-1].name == "get_invoice"
        assert request.tool_results[-1].content["status"] == "past_due"
        return WorkflowTurn(answer="The invoice is past due; payment guidance follows.")


def test_three_tool_billing_workflow_gets_a_tools_empty_final_synthesis_turn() -> None:
    gateway = ThreeToolBillingGateway()
    graph = ServiceDeskGraph(BusinessTools(BusinessRepository.from_default_seed()), gateway)

    result = graph.invoke(
        "cus_willow_002", "Why is our invoice past due, and what payment guidance applies?"
    )

    assert result["answer"] == "The invoice is past due; payment guidance follows."
    assert [record["name"] for record in result["tool_calls"]] == [
        "get_customer",
        "get_customer",
        "get_subscription",
        "get_invoice",
    ]
    assert len(gateway.requests) == 4
    assert all(request.tools for request in gateway.requests[:3])
    assert gateway.requests[-1].tools == ()
    assert [result.name for result in gateway.requests[-1].tool_results] == [
        "get_customer",
        "get_subscription",
        "get_invoice",
    ]


class FinalSynthesisToolRequestGateway(ThreeToolBillingGateway):
    def next_workflow_turn(self, request: WorkflowRequest) -> WorkflowTurn:
        self.requests.append(request)
        request_number = len(self.requests)
        if request_number <= len(self._calls):
            return WorkflowTurn(tool_calls=(self._calls[request_number - 1],))
        assert request.tools == ()
        return WorkflowTurn(
            tool_calls=(ToolCall(name="get_invoice", arguments={"invoice_id": "inv_willow_2001"}),)
        )


class CountingBusinessTools(BusinessTools):
    def __init__(self, repository: BusinessRepository) -> None:
        super().__init__(repository)
        self.invoice_calls = 0

    def get_invoice(self, invoice_id: str):
        self.invoice_calls += 1
        return super().get_invoice(invoice_id)


def test_answer_only_turn_rejects_a_fourth_tool_without_executing_it() -> None:
    tools = CountingBusinessTools(BusinessRepository.from_default_seed())
    graph = ServiceDeskGraph(tools, FinalSynthesisToolRequestGateway())

    with pytest.raises(WorkflowBoundedError) as error:
        graph.invoke("cus_willow_002", "Why is our invoice past due?")

    assert tools.invoice_calls == 1
    assert error.value.diagnostics == {
        "selected_route": "billing",
        "partial_workflow_tool_calls": [
            {"name": "get_customer", "status": "success"},
            {"name": "get_subscription", "status": "success"},
            {"name": "get_invoice", "status": "success"},
        ],
        "tool_result_statuses": [
            {"name": "get_customer", "status": "success"},
            {"name": "get_subscription", "status": "success"},
            {"name": "get_invoice", "status": "success"},
        ],
        "exhaustion_reason": "answer_only_turn_requested_tool",
        "attempted_tool_names": ["get_invoice"],
    }


class DuplicateToolGateway(FakeModelGateway):
    def next_workflow_turn(self, request: WorkflowRequest) -> WorkflowTurn:
        self.requests.append(request)
        if len(self.requests) <= 3:
            return WorkflowTurn(tool_calls=(ToolCall(name="get_customer"),))
        assert request.tools == ()
        return WorkflowTurn(answer="Answer after three duplicate calls.")


def test_duplicate_tool_calls_still_consume_the_three_call_budget() -> None:
    gateway = DuplicateToolGateway(route="billing")
    graph = ServiceDeskGraph(BusinessTools(BusinessRepository.from_default_seed()), gateway)

    result = graph.invoke("cus_willow_002", "Why is our invoice past due?")

    assert [record["name"] for record in result["tool_calls"][1:]] == [
        "get_customer",
        "get_customer",
        "get_customer",
    ]
    assert len(gateway.requests) == 4
    assert gateway.requests[-1].tools == ()


def test_bounded_synthesis_keeps_support_and_technical_tool_permissions_unchanged() -> None:
    assert WORKFLOW_ALLOWLISTS["support"] == ("get_customer", "list_tickets")
    assert WORKFLOW_ALLOWLISTS["technical"] == (
        "get_customer",
        "get_subscription",
        "list_tickets",
    )


class CrossCustomerInvoiceGateway(FakeModelGateway):
    def next_workflow_turn(self, request: WorkflowRequest) -> WorkflowTurn:
        self.requests.append(request)
        if not request.tool_results:
            return WorkflowTurn(
                tool_calls=(ToolCall(name="get_invoice", arguments={"invoice_id": "inv_willow_2001"}),)
            )
        return WorkflowTurn(answer="The other customer's invoice is unavailable.")


def test_bounded_synthesis_does_not_relax_cross_customer_invoice_denial() -> None:
    gateway = CrossCustomerInvoiceGateway(route="billing")
    graph = ServiceDeskGraph(BusinessTools(BusinessRepository.from_default_seed()), gateway)

    result = graph.invoke("cus_orbit_001", "Show invoice inv_willow_2001")

    assert result["tool_calls"][-1] == {"name": "get_invoice", "status": "denied"}
    assert gateway.requests[-1].tool_results[0].content == {
        "reason": "invoice_not_owned_by_customer"
    }
