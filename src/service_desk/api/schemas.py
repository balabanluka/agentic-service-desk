"""Public API schemas."""

from pydantic import BaseModel, Field

from service_desk.services.chat import ExecutionMetadata
from service_desk.ticketing.models import ActionStatus, ActionType


class HealthResponse(BaseModel):
    status: str


class ChatRequest(BaseModel):
    customer_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=4_000)


class ChatResponse(BaseModel):
    answer: str
    execution: ExecutionMetadata


class ErrorResponse(BaseModel):
    detail: str
    code: str


class ActionDecisionRequest(BaseModel):
    customer_id: str = Field(min_length=1, max_length=100)


class AuditEventResponse(BaseModel):
    event_id: int
    event_type: str
    actor_type: str
    metadata: dict[str, object]
    created_at: str


class ActionResponse(BaseModel):
    action_id: str
    customer_id: str
    route: str
    action_type: ActionType
    payload: dict[str, object]
    status: ActionStatus
    approval_required: bool
    expires_at: str
    result: dict[str, object] | None = None
    error_code: str | None = None
    audit_events: list[AuditEventResponse] = Field(default_factory=list)
