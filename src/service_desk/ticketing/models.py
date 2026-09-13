"""Typed V3 ticket mutations and durable approval records."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from service_desk.ai.gateway import RouteName
from service_desk.domain.models import Ticket


TicketStatus = Literal["open", "in_progress", "resolved"]
TicketPriority = Literal["critical", "high", "normal", "low"]
ActionType = Literal["create_ticket", "update_ticket_status", "update_ticket_priority"]
ActionStatus = Literal[
    "pending", "approved", "executing", "succeeded", "failed", "rejected", "expired"
]


class CreateTicketPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = Field(min_length=5, max_length=200)
    category: RouteName
    priority: TicketPriority = "normal"


class UpdateTicketStatusPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ticket_id: str = Field(pattern=r"^tic_[a-z]+_[a-z0-9]{4,32}$")
    status: TicketStatus


class UpdateTicketPriorityPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ticket_id: str = Field(pattern=r"^tic_[a-z]+_[a-z0-9]{4,32}$")
    priority: TicketPriority


class TicketAction(BaseModel):
    """Canonical action persisted before any business mutation occurs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action_id: str = Field(pattern=r"^act_[0-9a-f]{32}$")
    customer_id: str
    route: RouteName
    action_type: ActionType
    payload: dict[str, object]
    status: ActionStatus
    approval_required: bool = True
    proposed_by_request_id: str
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    result: dict[str, object] | None = None
    error_code: str | None = None

    @model_validator(mode="after")
    def has_valid_canonical_payload(self) -> "TicketAction":
        validate_action_payload(self.action_type, self.payload)
        if not self.approval_required:
            raise ValueError("ticket write actions must require approval")
        return self


class TicketMutationResult(BaseModel):
    """Sanitized idempotent result returned by an MCP write tool."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action_id: str
    action_type: ActionType
    ticket: Ticket
    replayed: bool = False


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: int
    action_id: str
    event_type: str
    actor_type: Literal["model", "human", "system", "mcp"]
    metadata: dict[str, object]
    created_at: datetime


def validate_action_payload(action_type: ActionType, payload: dict[str, object]) -> BaseModel:
    model = {
        "create_ticket": CreateTicketPayload,
        "update_ticket_status": UpdateTicketStatusPayload,
        "update_ticket_priority": UpdateTicketPriorityPayload,
    }[action_type]
    return model.model_validate(payload)
