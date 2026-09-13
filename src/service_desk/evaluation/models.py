"""Versioned schemas for synthetic V2 evaluation datasets."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from service_desk.ai.gateway import RouteName
from service_desk.ticketing.models import ActionStatus


class RetrievalCase(BaseModel):
    case_id: str = Field(pattern=r"^[a-z0-9-]+$")
    query: str = Field(min_length=1)
    expected_domain: RouteName | None = None
    expected_document_ids: tuple[str, ...] = ()
    acceptable_chunk_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def has_relevance_target(self) -> "RetrievalCase":
        if not self.expected_document_ids and not self.acceptable_chunk_ids:
            raise ValueError("retrieval cases require a document or chunk relevance target")
        return self


class RetrievalDataset(BaseModel):
    dataset_id: str = Field(pattern=r"^[a-z0-9-]+$")
    dataset_version: str
    corpus_version: str
    chunking_version: str
    embedding_model: str
    cases: tuple[RetrievalCase, ...] = Field(min_length=1)


class PlannedToolCall(BaseModel):
    name: str
    arguments: dict[str, object] = Field(default_factory=dict)


class ToolFactExpectation(BaseModel):
    tool_name: str
    field: str
    expected: object


SafetyExpectation = Literal["cross_customer_denied", "forbidden_tool_blocked"]


class WorkflowCase(BaseModel):
    case_id: str = Field(pattern=r"^[a-z0-9-]+$")
    customer_id: str
    message: str = Field(min_length=1)
    expected_route: RouteName | Literal["clarification"]
    needs_clarification: bool
    planned_tool_calls: tuple[PlannedToolCall, ...] = ()
    required_tools: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    expected_tool_statuses: dict[str, str] = Field(default_factory=dict)
    required_customer_facts: tuple[ToolFactExpectation, ...] = ()
    expected_knowledge_document_ids: tuple[str, ...] = ()
    safety_expectation: SafetyExpectation | None = None

    @model_validator(mode="after")
    def has_consistent_clarification_expectation(self) -> "WorkflowCase":
        if self.needs_clarification != (self.expected_route == "clarification"):
            raise ValueError("clarification route and needs_clarification must agree")
        if self.needs_clarification and self.planned_tool_calls:
            raise ValueError("clarification cases cannot plan workflow tool calls")
        return self


class WorkflowDataset(BaseModel):
    dataset_id: str = Field(pattern=r"^[a-z0-9-]+$")
    dataset_version: str
    corpus_version: str
    chunking_version: str
    embedding_model: str
    cases: tuple[WorkflowCase, ...] = Field(min_length=1)


class HeldOutManifest(BaseModel):
    manifest_version: str
    corpus_version: str
    chunking_version: str
    embedding_model: str
    files: dict[str, str] = Field(min_length=1)


ActionDecision = Literal["approve", "reject", "none"]
ActionSafetyExpectation = Literal[
    "no_write_before_approval",
    "rejection_no_mutation",
    "cross_customer_denied",
    "informational_no_action",
]


class EvaluationTicketFixture(BaseModel):
    ticket_id: str
    customer_id: str
    subject: str
    category: RouteName
    status: Literal["open", "in_progress", "resolved"]
    priority: Literal["critical", "high", "normal", "low"]


class ActionEvaluationCase(BaseModel):
    case_id: str = Field(pattern=r"^[a-z0-9-]+$")
    customer_id: str
    message: str = Field(min_length=1)
    expected_route: RouteName | Literal["clarification"]
    needs_clarification: bool
    expected_write_intents: tuple[str, ...] = ()
    expected_workflow_tool: str | None = None
    expected_workflow_status: str | None = None
    decision: ActionDecision = "none"
    expected_action_status: ActionStatus | None = None
    expected_mutation_count: int = Field(default=0, ge=0, le=1)
    expected_ticket_fields: dict[str, object] = Field(default_factory=dict)
    expected_knowledge_document_ids: tuple[str, ...] = ()
    safety_expectation: ActionSafetyExpectation | None = None
    setup_ticket: EvaluationTicketFixture | None = None
    verify_approval_replay: bool = False

    @model_validator(mode="after")
    def has_consistent_action_expectations(self) -> "ActionEvaluationCase":
        if self.needs_clarification != (self.expected_route == "clarification"):
            raise ValueError("clarification route and needs_clarification must agree")
        if self.expected_action_status is not None and self.expected_workflow_tool is None:
            raise ValueError("an action status requires an expected proposal tool")
        if self.decision == "approve" and self.expected_action_status != "succeeded":
            raise ValueError("approved benchmark actions must expect succeeded")
        if self.decision == "reject" and self.expected_action_status != "rejected":
            raise ValueError("rejected benchmark actions must expect rejected")
        return self


class ActionEvaluationDataset(BaseModel):
    dataset_id: str = Field(pattern=r"^[a-z0-9-]+$")
    dataset_version: str
    corpus_version: str
    chunking_version: str
    embedding_model: str
    cases: tuple[ActionEvaluationCase, ...] = Field(min_length=1)
