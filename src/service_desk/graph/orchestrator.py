"""The one controlled LangGraph orchestrator for V1."""

import logging
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from service_desk.ai.gateway import (
    KnowledgeSource,
    ModelGateway,
    ModelGatewayError,
    RouteName,
    ToolResult,
    WorkflowRequest,
    ensure_final_turn,
)
from service_desk.graph.state import AgentState, KnowledgeSourceRecord
from service_desk.graph.workflows.permissions import ScopedToolExecutor
from service_desk.knowledge.retrieval import KnowledgeSearchProvider, KnowledgeSearchResult
from service_desk.tools.business import BusinessTools

MAX_WORKFLOW_TOOL_TURNS = 3
MAX_WORKFLOW_TOOL_CALLS = 3

logger = logging.getLogger(__name__)


class WorkflowBoundedError(ModelGatewayError):
    """A safe diagnostic for a workflow blocked by its bounded execution rules."""

    def __init__(
        self,
        *,
        route: RouteName,
        tool_calls: list[dict[str, str]],
        tool_results: list[ToolResult],
        reason: str,
        attempted_tool_names: tuple[str, ...] = (),
    ) -> None:
        super().__init__(f"bounded workflow failed: {reason}")
        self.diagnostics = {
            "selected_route": route,
            "partial_workflow_tool_calls": [dict(record) for record in tool_calls],
            "tool_result_statuses": [
                {"name": result.name, "status": result.status} for result in tool_results
            ],
            "exhaustion_reason": reason,
            "attempted_tool_names": list(attempted_tool_names),
        }


class ServiceDeskGraph:
    def __init__(
        self,
        tools: BusinessTools,
        model_gateway: ModelGateway,
        knowledge_retriever: KnowledgeSearchProvider | None = None,
    ) -> None:
        self._tools = tools
        self._model_gateway = model_gateway
        self._knowledge_retriever = knowledge_retriever
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
                "knowledge_sources": [],
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

    def _run_workflow(self, state: AgentState, route: RouteName, node: str) -> dict[str, object]:
        executor = ScopedToolExecutor(self._tools, state["customer_id"], route)
        tool_results = list(state["tool_results"])
        initial_tool_calls = list(state["tool_calls"])
        workflow_tool_calls: list[dict[str, str]] = []
        knowledge_sources = self._retrieve_knowledge(state["message"], route)
        remaining_tool_calls = MAX_WORKFLOW_TOOL_CALLS
        for tool_turn_index in range(MAX_WORKFLOW_TOOL_TURNS):
            request = WorkflowRequest(
                route=route,
                message=state["message"],
                customer_id=state["customer_id"],
                tools=executor.definitions,
                tool_results=tuple(tool_results),
                knowledge_sources=knowledge_sources,
            )
            turn = ensure_final_turn(
                self._model_gateway.next_workflow_turn(request), executor.allowed_names
            )
            if turn.answer:
                return self._updated(
                    state,
                    node,
                    tool_calls=[*initial_tool_calls, *workflow_tool_calls],
                    tool_results=tool_results,
                    knowledge_sources=[_source_record(source) for source in knowledge_sources],
                    answer=turn.answer,
                    answer_source="model",
            )
            if len(turn.tool_calls) > remaining_tool_calls:
                raise WorkflowBoundedError(
                    route=route,
                    tool_calls=workflow_tool_calls,
                    tool_results=tool_results,
                    reason="tool_call_budget_exceeded",
                    attempted_tool_names=tuple(tool_call.name for tool_call in turn.tool_calls),
                )
            for tool_call in turn.tool_calls:
                result, record = executor.execute(tool_call)
                tool_results.append(result)
                workflow_tool_calls.append(record)
            remaining_tool_calls -= len(turn.tool_calls)
            if remaining_tool_calls == 0 or tool_turn_index == MAX_WORKFLOW_TOOL_TURNS - 1:
                return self._run_final_synthesis(
                    state=state,
                    route=route,
                    node=node,
                    initial_tool_calls=initial_tool_calls,
                    workflow_tool_calls=workflow_tool_calls,
                    tool_results=tool_results,
                    knowledge_sources=knowledge_sources,
                )
        raise AssertionError("workflow tool-use loop must return or synthesize")

    def _run_final_synthesis(
        self,
        *,
        state: AgentState,
        route: RouteName,
        node: str,
        initial_tool_calls: list[dict[str, str]],
        workflow_tool_calls: list[dict[str, str]],
        tool_results: list[ToolResult],
        knowledge_sources: tuple[KnowledgeSource, ...],
    ) -> dict[str, object]:
        """Give the model one tools-empty turn to answer from the bounded evidence."""

        request = WorkflowRequest(
            route=route,
            message=state["message"],
            customer_id=state["customer_id"],
            tools=(),
            tool_results=tuple(tool_results),
            knowledge_sources=knowledge_sources,
        )
        final_turn = self._model_gateway.next_workflow_turn(request)
        if final_turn.tool_calls:
            raise WorkflowBoundedError(
                route=route,
                tool_calls=workflow_tool_calls,
                tool_results=tool_results,
                reason="answer_only_turn_requested_tool",
                attempted_tool_names=tuple(tool_call.name for tool_call in final_turn.tool_calls),
            )
        if not final_turn.answer:
            raise WorkflowBoundedError(
                route=route,
                tool_calls=workflow_tool_calls,
                tool_results=tool_results,
                reason="answer_only_turn_missing_answer",
            )
        return self._updated(
            state,
            node,
            tool_calls=[*initial_tool_calls, *workflow_tool_calls],
            tool_results=tool_results,
            knowledge_sources=[_source_record(source) for source in knowledge_sources],
            answer=final_turn.answer,
            answer_source="model",
        )

    def _retrieve_knowledge(self, message: str, route: str) -> tuple[KnowledgeSource, ...]:
        """Retrieve route-scoped context without letting the model choose a domain."""

        if self._knowledge_retriever is None:
            return ()
        try:
            results = self._knowledge_retriever.search(message, domain=route)
        except Exception as error:  # Retrieval is optional context, never authority by itself.
            logger.warning(
                "Knowledge retrieval unavailable [route=%s, error_type=%s]",
                route,
                type(error).__name__,
            )
            return ()
        return tuple(
            _knowledge_source(result) for result in results if result.domain == route
        )

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


def _knowledge_source(result: KnowledgeSearchResult) -> KnowledgeSource:
    return KnowledgeSource(
        document_id=result.document_id,
        document_title=result.document_title,
        chunk_id=result.chunk_id,
        source_path=result.source_path,
        content=result.content,
    )


def _source_record(source: KnowledgeSource) -> KnowledgeSourceRecord:
    return {
        "document_id": source.document_id,
        "document_title": source.document_title,
        "chunk_id": source.chunk_id,
        "source_path": source.source_path,
    }
