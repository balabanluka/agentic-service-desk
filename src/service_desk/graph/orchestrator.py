"""The one controlled LangGraph orchestrator for V1."""

from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from service_desk.ai.gateway import ModelGateway, ModelGatewayError, WorkflowRequest, ensure_final_turn
from service_desk.graph.state import AgentState
from service_desk.graph.workflows.permissions import ScopedToolExecutor
from service_desk.tools.business import BusinessTools

MAX_WORKFLOW_TOOL_TURNS = 3
MAX_WORKFLOW_TOOL_CALLS = 3


class ServiceDeskGraph:
    def __init__(self, tools: BusinessTools, model_gateway: ModelGateway) -> None:
        self._tools = tools
        self._model_gateway = model_gateway
        self._graph = self._build_graph()

    def invoke(self, customer_id: str, message: str, request_id: str | None = None) -> AgentState:
        return self._graph.invoke(
            {
                "request_id": request_id or str(uuid4()),
                "customer_id": customer_id,
                "message": message,
                "transitions": [],
                "tool_calls": [],
                "tool_results": [],
            }
        )

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("load_customer", self._load_customer)
        graph.add_node("route_request", self._route_request)
        graph.add_node("support_workflow", self._run_support)
        graph.add_node("billing_workflow", self._run_billing)
        graph.add_node("technical_workflow", self._run_technical)
        graph.add_node("clarify", self._clarify)
        graph.add_node("customer_not_found", self._customer_not_found)
        graph.add_edge(START, "load_customer")
        graph.add_conditional_edges(
            "load_customer",
            lambda state: "customer_not_found" if state.get("error_code") else "route_request",
        )
        graph.add_conditional_edges(
            "route_request",
            self._route_edge,
            {
                "support": "support_workflow",
                "billing": "billing_workflow",
                "technical": "technical_workflow",
                "clarify": "clarify",
            },
        )
        for terminal in ("support_workflow", "billing_workflow", "technical_workflow", "clarify", "customer_not_found"):
            graph.add_edge(terminal, END)
        return graph.compile()

    @staticmethod
    def _updated(state: AgentState, node: str, **updates: object) -> dict[str, object]:
        return {
            "transitions": [*state["transitions"], node],
            **updates,
        }

    def _load_customer(self, state: AgentState) -> dict[str, object]:
        customer = self._tools.get_customer(state["customer_id"])
        records = [*state["tool_calls"], {"name": "get_customer", "status": "success" if customer else "not_found"}]
        if customer is None:
            return self._updated(
                state,
                "load_customer",
                tool_calls=records,
                error_code="customer_not_found",
            )
        return self._updated(state, "load_customer", tool_calls=records)

    def _route_request(self, state: AgentState) -> dict[str, object]:
        decision = self._model_gateway.route(state["message"])
        return self._updated(
            state,
            "route_request",
            selected_route=decision.route or "clarification",
            needs_clarification=decision.needs_clarification,
            route_rationale=decision.rationale,
            diagnostic_confidence=decision.diagnostic_confidence,
        )

    @staticmethod
    def _route_edge(state: AgentState) -> str:
        if state.get("needs_clarification"):
            return "clarify"
        return str(state["selected_route"])

    def _run_support(self, state: AgentState) -> dict[str, object]:
        return self._run_workflow(state, "support", "support_workflow")

    def _run_billing(self, state: AgentState) -> dict[str, object]:
        return self._run_workflow(state, "billing", "billing_workflow")

    def _run_technical(self, state: AgentState) -> dict[str, object]:
        return self._run_workflow(state, "technical", "technical_workflow")

    def _run_workflow(self, state: AgentState, route: str, node: str) -> dict[str, object]:
        executor = ScopedToolExecutor(self._tools, state["customer_id"], route)  # type: ignore[arg-type]
        tool_results = list(state["tool_results"])
        tool_calls = list(state["tool_calls"])
        remaining_tool_calls = MAX_WORKFLOW_TOOL_CALLS
        for _ in range(MAX_WORKFLOW_TOOL_TURNS):
            request = WorkflowRequest(
                route=route,  # type: ignore[arg-type]
                message=state["message"],
                customer_id=state["customer_id"],
                tools=executor.definitions,
                tool_results=tuple(tool_results),
            )
            turn = ensure_final_turn(
                self._model_gateway.next_workflow_turn(request), executor.allowed_names
            )
            if turn.answer:
                return self._updated(
                    state,
                    node,
                    tool_calls=tool_calls,
                    tool_results=tool_results,
                    answer=turn.answer,
                    answer_source="model",
                )
            if len(turn.tool_calls) > remaining_tool_calls:
                raise ModelGatewayError("workflow exceeded its bounded tool-call budget")
            for tool_call in turn.tool_calls:
                result, record = executor.execute(tool_call)
                tool_results.append(result)
                tool_calls.append(record)
            remaining_tool_calls -= len(turn.tool_calls)
        raise ModelGatewayError("workflow exhausted its bounded tool-use loop")

    def _clarify(self, state: AgentState) -> dict[str, object]:
        return self._updated(
            state,
            "clarify",
            answer="Could you clarify whether you need support, billing, or technical help?",
            answer_source="template",
        )

    def _customer_not_found(self, state: AgentState) -> dict[str, object]:
        return self._updated(
            state,
            "customer_not_found",
            answer="We could not find that customer account.",
            answer_source="template",
        )
