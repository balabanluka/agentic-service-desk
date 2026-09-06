"""Application service that turns a graph state into API-safe output."""

from pydantic import BaseModel, Field

from service_desk.graph.orchestrator import ServiceDeskGraph


class CustomerNotFoundError(ValueError):
    pass


class KnowledgeSourceMetadata(BaseModel):
    document_id: str
    document_title: str
    chunk_id: str
    source_path: str


class ExecutionMetadata(BaseModel):
    request_id: str
    selected_route: str | None
    tools_used: list[str]
    graph_path: list[str]
    answer_source: str
    diagnostic_confidence: float | None = None
    knowledge_sources: list[KnowledgeSourceMetadata] = Field(default_factory=list)


class ChatResult(BaseModel):
    answer: str
    execution: ExecutionMetadata


class ChatService:
    def __init__(self, graph: ServiceDeskGraph) -> None:
        self._graph = graph

    def chat(self, customer_id: str, message: str) -> ChatResult:
        state = self._graph.invoke(customer_id, message)
        if state.get("error_code") == "customer_not_found":
            raise CustomerNotFoundError(customer_id)
        return ChatResult(
            answer=state["answer"],
            execution=ExecutionMetadata(
                request_id=state["request_id"],
                selected_route=state.get("selected_route"),
                tools_used=[record["name"] for record in state["tool_calls"]],
                graph_path=state["transitions"],
                answer_source=state["answer_source"],
                diagnostic_confidence=state.get("diagnostic_confidence"),
                knowledge_sources=state.get("knowledge_sources", []),
            ),
        )
