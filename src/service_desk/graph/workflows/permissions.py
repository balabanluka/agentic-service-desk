"""Strict, per-domain read-only tool definitions and execution."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from service_desk.ai.gateway import RouteName, ToolCall, ToolResult
from service_desk.graph.state import ToolCallRecord
from service_desk.tools.business import BusinessTools


class NoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InvoiceArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_id: str


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
}

WORKFLOW_ALLOWLISTS: dict[RouteName, tuple[str, ...]] = {
    "support": ("get_customer", "list_tickets"),
    "billing": ("get_customer", "get_subscription", "get_invoice"),
    "technical": ("get_customer", "get_subscription", "list_tickets"),
}


class ScopedToolExecutor:
    """Executes only an allowlisted tool against the current customer context."""

    def __init__(self, tools: BusinessTools, customer_id: str, route: RouteName) -> None:
        self._tools = tools
        self._customer_id = customer_id
        self._allowed = WORKFLOW_ALLOWLISTS[route]

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
            else:  # list_tickets
                NoArguments.model_validate(call.arguments)
                value = self._tools.list_tickets(self._customer_id)
        except ValidationError:
            return self._result(call.name, "invalid_arguments", {"reason": "invalid_arguments"})

        if value is None:
            return self._result(call.name, "not_found", {"found": False})
        if isinstance(value, tuple):
            content = {"items": [item.model_dump(mode="json") for item in value]}
        else:
            content = value.model_dump(mode="json")
        return self._result(call.name, "success", content)

    @staticmethod
    def _result(
        name: str,
        status: Literal["success", "not_found", "denied", "invalid_arguments"],
        content: dict[str, object],
    ) -> tuple[ToolResult, ToolCallRecord]:
        return ToolResult(name=name, status=status, content=content), {"name": name, "status": status}
