from service_desk.ai.gateway import RouteDecision, ToolCall, WorkflowRequest, WorkflowTurn


class FakeModelGateway:
    """Offline deterministic model double used by graph and API tests."""

    def __init__(self, route: str = "support", clarification: bool = False) -> None:
        self.route_name = route
        self.clarification = clarification
        self.requests: list[WorkflowRequest] = []

    def route(self, message: str) -> RouteDecision:
        if self.clarification:
            return RouteDecision(
                needs_clarification=True,
                rationale="The question mixes unrelated concerns.",
                diagnostic_confidence=0.25,
            )
        return RouteDecision(
            route=self.route_name,  # type: ignore[arg-type]
            needs_clarification=False,
            rationale="Test-selected route.",
            diagnostic_confidence=0.9,
        )

    def next_workflow_turn(self, request: WorkflowRequest) -> WorkflowTurn:
        self.requests.append(request)
        if not request.tool_results:
            first_tool = {
                "support": "list_tickets",
                "billing": "get_subscription",
                "technical": "list_tickets",
            }[request.route]
            return WorkflowTurn(tool_calls=(ToolCall(name=first_tool),))
        return WorkflowTurn(answer=f"Offline {request.route} answer based on local tools.")
