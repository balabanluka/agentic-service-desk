"""State carried through the single service-desk graph."""

from typing import NotRequired, TypedDict

from service_desk.ai.gateway import RouteName, ToolResult


class ToolCallRecord(TypedDict):
    name: str
    status: str


class KnowledgeSourceRecord(TypedDict):
    document_id: str
    document_title: str
    chunk_id: str
    source_path: str


class PendingActionRecord(TypedDict):
    action_id: str
    action_type: str
    status: str
    approval_required: bool
    expires_at: str


class AgentState(TypedDict):
    request_id: str
    customer_id: str
    message: str
    transitions: list[str]
    tool_calls: list[ToolCallRecord]
    tool_results: list[ToolResult]
    knowledge_sources: NotRequired[list[KnowledgeSourceRecord]]
    pending_actions: NotRequired[list[PendingActionRecord]]
    selected_route: NotRequired[RouteName | str]
    needs_clarification: NotRequired[bool]
    route_rationale: NotRequired[str]
    diagnostic_confidence: NotRequired[float | None]
    answer: NotRequired[str]
    answer_source: NotRequired[str]
    error_code: NotRequired[str]
