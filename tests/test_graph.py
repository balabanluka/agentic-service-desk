import pytest

from service_desk.ai.gateway import ToolCall, WorkflowRequest, WorkflowTurn
from service_desk.data.repository import BusinessRepository
from service_desk.graph.orchestrator import ServiceDeskGraph
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
