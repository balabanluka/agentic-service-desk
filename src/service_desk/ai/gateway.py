"""Small model boundary that keeps the graph independently testable."""

from collections.abc import Sequence
from typing import Literal, Protocol

from pydantic import BaseModel, Field


RouteName = Literal["support", "billing", "technical"]


class RouteDecision(BaseModel):
    """A routing instruction, not a calibrated probability estimate."""

    route: RouteName | None = None
    needs_clarification: bool
    rationale: str = Field(min_length=1, max_length=500)
    diagnostic_confidence: float | None = Field(default=None, ge=0, le=1)


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, object] = Field(default_factory=dict)


class ToolResult(BaseModel):
    name: str
    status: Literal["success", "not_found", "denied", "invalid_arguments"]
    content: dict[str, object]


class KnowledgeSource(BaseModel):
    """Retrieved knowledge context available to one controlled workflow."""

    document_id: str
    document_title: str
    chunk_id: str
    source_path: str
    content: str


class WorkflowTurn(BaseModel):
    """The next bounded action selected by the model inside one workflow."""

    tool_calls: tuple[ToolCall, ...] = ()
    answer: str | None = None


class WorkflowRequest(BaseModel):
    route: RouteName
    message: str
    customer_id: str
    tools: tuple[dict[str, object], ...]
    tool_results: tuple[ToolResult, ...] = ()
    knowledge_sources: tuple[KnowledgeSource, ...] = ()


class ModelGatewayError(RuntimeError):
    """Raised when a model response cannot safely drive the graph."""

    def __init__(self, message: str, *, operation: str | None = None) -> None:
        super().__init__(message)
        self.operation = operation


class ModelGateway(Protocol):
    def route(self, message: str) -> RouteDecision:
        """Choose a graph route or explicitly request clarification."""

    def next_workflow_turn(self, request: WorkflowRequest) -> WorkflowTurn:
        """Choose scoped tool calls or provide the final workflow answer."""


def require_valid_route(decision: RouteDecision) -> RouteDecision:
    if decision.needs_clarification and decision.route is not None:
        raise ModelGatewayError("clarification decisions must not select a route")
    if not decision.needs_clarification and decision.route is None:
        raise ModelGatewayError("routing decisions must select a route")
    return decision


def ensure_final_turn(turn: WorkflowTurn, allowed_tool_names: Sequence[str]) -> WorkflowTurn:
    unknown = {tool_call.name for tool_call in turn.tool_calls} - set(allowed_tool_names)
    if unknown:
        raise ModelGatewayError(f"model requested tools outside the allowlist: {sorted(unknown)}")
    if turn.tool_calls and turn.answer:
        raise ModelGatewayError("a workflow turn cannot call tools and answer simultaneously")
    if not turn.tool_calls and not turn.answer:
        raise ModelGatewayError("a workflow turn must call a tool or provide an answer")
    return turn
