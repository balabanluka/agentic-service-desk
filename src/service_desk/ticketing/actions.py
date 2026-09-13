"""Durable proposal, approval, rejection, and MCP execution service."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from service_desk.ai.gateway import RouteName
from service_desk.ticketing.mcp import (
    TicketGateway,
    TicketMcpToolError,
    TicketMcpUnavailable,
)
from service_desk.ticketing.models import (
    ActionType,
    AuditEvent,
    CreateTicketPayload,
    TicketAction,
    UpdateTicketPriorityPayload,
    UpdateTicketStatusPayload,
    validate_action_payload,
)
from service_desk.ticketing.repository import ActionRepository, TERMINAL_ACTION_STATUSES


class ActionNotFoundError(LookupError):
    pass


class ActionProposalError(RuntimeError):
    """A proposed action failed deterministic scope or ownership validation."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ActionExecutionUnavailable(RuntimeError):
    """Execution outcome is unresolved; the same approval may be retried safely."""

    def __init__(self, action: TicketAction) -> None:
        super().__init__("approved action execution is temporarily unavailable")
        self.action = action


class ActionService:
    """Application-owned control plane; business writes remain behind MCP."""

    def __init__(
        self,
        *,
        database_url: str,
        ticket_gateway: TicketGateway,
        ttl_minutes: int = 30,
    ) -> None:
        self._database_url = database_url
        self._ticket_gateway = ticket_gateway
        self._ttl = timedelta(minutes=ttl_minutes)

    def propose(
        self,
        *,
        customer_id: str,
        route: RouteName,
        action_type: ActionType,
        payload: dict[str, object],
        request_id: str,
    ) -> TicketAction:
        parsed = validate_action_payload(action_type, payload)
        if isinstance(parsed, CreateTicketPayload):
            if parsed.category != route:
                raise ActionProposalError("action_domain_mismatch")
        else:
            assert isinstance(parsed, (UpdateTicketStatusPayload, UpdateTicketPriorityPayload))
            try:
                ticket = self._ticket_gateway.get_ticket(customer_id, parsed.ticket_id)
            except TicketMcpUnavailable as error:
                raise ActionProposalError("ticket_service_unavailable") from error
            if ticket is None:
                raise ActionProposalError("ticket_not_available")
            if ticket.category != route:
                raise ActionProposalError("action_domain_mismatch")

        canonical_payload = parsed.model_dump(mode="json")
        proposal_key = _proposal_key(
            request_id=request_id,
            customer_id=customer_id,
            route=route,
            action_type=action_type,
            payload=canonical_payload,
        )
        repository = ActionRepository.connect(self._database_url)
        try:
            return repository.create_pending(
                action_id=f"act_{uuid4().hex}",
                customer_id=customer_id,
                route=route,
                action_type=action_type,
                payload=canonical_payload,
                proposed_by_request_id=request_id,
                proposal_key=proposal_key,
                expires_at=datetime.now(UTC) + self._ttl,
            )
        finally:
            repository.close()

    def get(self, action_id: str, customer_id: str) -> TicketAction:
        repository = ActionRepository.connect(self._database_url)
        try:
            action = repository.get_for_customer(action_id, customer_id)
        finally:
            repository.close()
        if action is None:
            raise ActionNotFoundError(action_id)
        return action

    def approve(self, action_id: str, customer_id: str) -> TicketAction:
        repository = ActionRepository.connect(self._database_url)
        try:
            action = repository.begin_approval(action_id, customer_id)
        finally:
            repository.close()
        if action is None:
            raise ActionNotFoundError(action_id)
        if action.status in TERMINAL_ACTION_STATUSES:
            return action

        try:
            result = self._ticket_gateway.execute(action.action_id, action.action_type)
        except TicketMcpUnavailable:
            repository = ActionRepository.connect(self._database_url)
            try:
                repository.record_execution_deferred(action.action_id, "mcp_unavailable")
                unresolved = repository.get_for_customer(action.action_id, customer_id)
                assert unresolved is not None
            finally:
                repository.close()
            raise ActionExecutionUnavailable(unresolved)
        except TicketMcpToolError as error:
            repository = ActionRepository.connect(self._database_url)
            try:
                return repository.mark_failed(action.action_id, error.code)
            finally:
                repository.close()

        repository = ActionRepository.connect(self._database_url)
        try:
            return repository.mark_succeeded(action.action_id, result)
        finally:
            repository.close()

    def reject(self, action_id: str, customer_id: str) -> TicketAction:
        repository = ActionRepository.connect(self._database_url)
        try:
            action = repository.reject(action_id, customer_id)
        finally:
            repository.close()
        if action is None:
            raise ActionNotFoundError(action_id)
        return action

    def audit(self, action_id: str, customer_id: str) -> tuple[AuditEvent, ...]:
        repository = ActionRepository.connect(self._database_url)
        try:
            if repository.get_for_customer(action_id, customer_id) is None:
                raise ActionNotFoundError(action_id)
            return repository.audit_events(action_id, customer_id)
        finally:
            repository.close()


def _proposal_key(
    *,
    request_id: str,
    customer_id: str,
    route: RouteName,
    action_type: ActionType,
    payload: dict[str, object],
) -> str:
    canonical = json.dumps(
        {
            "request_id": request_id,
            "customer_id": customer_id,
            "route": route,
            "action_type": action_type,
            "payload": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()
