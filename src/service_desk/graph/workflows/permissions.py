"""Strict, per-domain read-only tool definitions and execution."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from service_desk.ai.gateway import RouteName, ToolCall, ToolResult
from service_desk.graph.state import ToolCallRecord
from service_desk.tools.business import BusinessTools
from service_desk.ticketing.actions import ActionProposalError, ActionService
from service_desk.ticketing.mcp import TicketMcpUnavailable


class NoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InvoiceArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_id: str


class CreateTicketArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str
    priority: Literal["critical", "high", "normal", "low"]


class UpdateTicketStatusArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_id: str
    status: Literal["open", "in_progress", "resolved"]


class UpdateTicketPriorityArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_id: str
    priority: Literal["critical", "high", "normal", "low"]


@dataclass(frozen=True, slots=True)
class ToolPolicy:
    effect: Literal["read", "write_proposal"]
    approval_required: bool


TOOL_POLICIES: dict[str, ToolPolicy] = {
    "get_customer": ToolPolicy(effect="read", approval_required=False),
    "get_subscription": ToolPolicy(effect="read", approval_required=False),
    "get_invoice": ToolPolicy(effect="read", approval_required=False),
    "list_tickets": ToolPolicy(effect="read", approval_required=False),
    "propose_create_ticket": ToolPolicy(effect="write_proposal", approval_required=True),
    "propose_update_ticket_status": ToolPolicy(effect="write_proposal", approval_required=True),
    "propose_update_ticket_priority": ToolPolicy(effect="write_proposal", approval_required=True),
}


TOOL_DEFINITIONS: dict[str, dict[str, object]] = {
    "get_customer": {
        "type": "function",
        "name": "get_customer",
        "description": "Get the current authenticated customer's profile.",
        "parameters": NoArguments.model_json_schema(),
        "strict": True,
    },
    "get_subscription": {
        "type": "function",
        "name": "get_subscription",
        "description": "Get the current customer's subscription and invoice references.",
        "parameters": NoArguments.model_json_schema(),
        "strict": True,
    },
    "get_invoice": {
        "type": "function",
        "name": "get_invoice",
        "description": "Get one invoice belonging to the current customer by invoice ID.",
        "parameters": InvoiceArguments.model_json_schema(),
        "strict": True,
    },
    "list_tickets": {
        "type": "function",
        "name": "list_tickets",
        "description": "List the current customer's existing support tickets.",
        "parameters": NoArguments.model_json_schema(),
        "strict": True,
    },
    "propose_create_ticket": {
        "type": "function",
        "name": "propose_create_ticket",
        "description": (
            "Create a pending, approval-required ticket action only when the user explicitly "
            "asks to create/open/file a ticket. This does not create the ticket. Never use for "
            "questions, examples, hypotheticals, or requests for guidance."
        ),
        "parameters": CreateTicketArguments.model_json_schema(),
        "strict": True,
    },
    "propose_update_ticket_status": {
        "type": "function",
        "name": "propose_update_ticket_status",
        "description": (
            "Create a pending, approval-required status change only when the user explicitly "
            "asks to change a ticket status. This does not update the ticket."
        ),
        "parameters": UpdateTicketStatusArguments.model_json_schema(),
        "strict": True,
    },
    "propose_update_ticket_priority": {
        "type": "function",
        "name": "propose_update_ticket_priority",
        "description": (
            "Create a pending, approval-required priority change only when the user explicitly "
            "asks to change a ticket priority. This does not update the ticket."
        ),
        "parameters": UpdateTicketPriorityArguments.model_json_schema(),
        "strict": True,
    },
}

WORKFLOW_ALLOWLISTS: dict[RouteName, tuple[str, ...]] = {
    "support": ("get_customer", "list_tickets"),
    "billing": ("get_customer", "get_subscription", "get_invoice"),
    "technical": ("get_customer", "get_subscription", "list_tickets"),
}

ACTION_PROPOSAL_TOOLS = (
    "propose_create_ticket",
    "propose_update_ticket_status",
    "propose_update_ticket_priority",
)

PROPOSAL_TOOL_BY_INTENT = {
    "create_ticket": "propose_create_ticket",
    "update_ticket_status": "propose_update_ticket_status",
    "update_ticket_priority": "propose_update_ticket_priority",
}


class ScopedToolExecutor:
    """Executes only an allowlisted tool against the current customer context."""

    def __init__(
        self,
        tools: BusinessTools,
        customer_id: str,
        route: RouteName,
        *,
        action_service: ActionService | None = None,
        request_id: str = "",
        write_intents: tuple[str, ...] = (),
    ) -> None:
        self._tools = tools
        self._customer_id = customer_id
        self._route = route
        self._action_service = action_service
        self._request_id = request_id
        proposed_tools = tuple(
            PROPOSAL_TOOL_BY_INTENT[intent]
            for intent in dict.fromkeys(write_intents)
            if intent in PROPOSAL_TOOL_BY_INTENT
        )
        self._allowed = WORKFLOW_ALLOWLISTS[route] + (
            proposed_tools if action_service is not None else ()
        )

    @property
    def definitions(self) -> tuple[dict[str, object], ...]:
        return tuple(TOOL_DEFINITIONS[name] for name in self._allowed)

    @property
    def allowed_names(self) -> tuple[str, ...]:
        return self._allowed

    def execute(self, call: ToolCall) -> tuple[ToolResult, ToolCallRecord]:
        if call.name not in self._allowed:
            return self._result(call.name, "denied", {"reason": "tool_not_allowed"})

        try:
            if call.name == "get_customer":
                NoArguments.model_validate(call.arguments)
                value = self._tools.get_customer(self._customer_id)
            elif call.name == "get_subscription":
                NoArguments.model_validate(call.arguments)
                value = self._tools.get_subscription(self._customer_id)
            elif call.name == "get_invoice":
                arguments = InvoiceArguments.model_validate(call.arguments)
                value = self._tools.get_invoice(arguments.invoice_id)
                if value is not None and value.customer_id != self._customer_id:
                    return self._result(call.name, "denied", {"reason": "invoice_not_owned_by_customer"})
            elif call.name == "list_tickets":
                NoArguments.model_validate(call.arguments)
                value = self._tools.list_tickets(self._customer_id)
            else:
                return self._propose(call)
        except ValidationError:
            return self._result(call.name, "invalid_arguments", {"reason": "invalid_arguments"})
        except TicketMcpUnavailable:
            return self._result(call.name, "unavailable", {"reason": "ticket_service_unavailable"})

        if value is None:
            return self._result(call.name, "not_found", {"found": False})
        if isinstance(value, tuple):
            content = {"items": [item.model_dump(mode="json") for item in value]}
        else:
            content = value.model_dump(mode="json")
        return self._result(call.name, "success", content)

    def _propose(self, call: ToolCall) -> tuple[ToolResult, ToolCallRecord]:
        if self._action_service is None:
            return self._result(call.name, "denied", {"reason": "actions_unavailable"})
        try:
            if call.name == "propose_create_ticket":
                arguments = CreateTicketArguments.model_validate(call.arguments)
                action_type = "create_ticket"
                payload = {**arguments.model_dump(), "category": self._route}
            elif call.name == "propose_update_ticket_status":
                arguments = UpdateTicketStatusArguments.model_validate(call.arguments)
                action_type = "update_ticket_status"
                payload = arguments.model_dump()
            else:
                arguments = UpdateTicketPriorityArguments.model_validate(call.arguments)
                action_type = "update_ticket_priority"
                payload = arguments.model_dump()
            action = self._action_service.propose(
                customer_id=self._customer_id,
                route=self._route,
                action_type=action_type,
                payload=payload,
                request_id=self._request_id,
            )
        except ValidationError:
            return self._result(call.name, "invalid_arguments", {"reason": "invalid_arguments"})
        except ActionProposalError as error:
            status = "unavailable" if error.code == "ticket_service_unavailable" else "denied"
            return self._result(call.name, status, {"reason": error.code})
        return self._result(
            call.name,
            "pending_approval",
            {
                "action_id": action.action_id,
                "action_type": action.action_type,
                "status": action.status,
                "approval_required": action.approval_required,
                "expires_at": action.expires_at.isoformat(),
            },
        )

    @staticmethod
    def _result(
        name: str,
        status: Literal[
            "success", "not_found", "denied", "invalid_arguments", "pending_approval", "unavailable"
        ],
        content: dict[str, object],
    ) -> tuple[ToolResult, ToolCallRecord]:
        return ToolResult(name=name, status=status, content=content), {"name": name, "status": status}
