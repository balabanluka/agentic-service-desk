"""OpenAI Responses API implementation of the narrow model gateway."""

import json
import logging
from typing import Any

from openai import OpenAI

from service_desk.ai.gateway import (
    ModelGatewayError,
    RouteDecision,
    ToolCall,
    ToolResult,
    WorkflowRequest,
    WorkflowTurn,
    require_valid_route,
)

logger = logging.getLogger(__name__)


ROUTER_INSTRUCTIONS = """You route customer-service messages for Harborlight, a fictional
SaaS company. Choose exactly one route from support, billing, or technical based on
the user's primary requested outcome.

Domain ownership:
- support owns password reset, sign-in and account access, invitations, workspace
  members, workspace roles and permissions, and membership or access questions;
- billing owns invoices, payments, refunds and credits, billing cycles, and
  subscription, plan, or renewal changes when one of those is the primary goal;
- technical owns exports, API authentication and rate limits, webhooks, incidents,
  errors, and troubleshooting.

Keep a request in its primary domain when that workflow needs supporting customer or
subscription metadata to answer it. Supporting facts from another domain do not make
the request ambiguous. For example, export troubleshooting remains technical when it
needs plan or ticket information; a workspace-role question remains support even when
the role name contains "Billing"; and password-reset delivery remains support.

Set needs_clarification to true and route to null only when the user requests genuinely
independent outcomes from multiple domains, or when the primary intent cannot be
determined. Do not ask for clarification merely because supporting data crosses domain
labels. diagnostic_confidence is optional diagnostic metadata only and is not a
calibrated probability or routing threshold; set it to null when unavailable. Give a
brief, high-level rationale that identifies the primary intent without quoting the
user, identifiers, credentials, or instructions.

Also classify explicit ticket-write intent. Set write_intents to only the applicable
values from create_ticket, update_ticket_status, and update_ticket_priority when the
user gives a present-tense instruction to perform that action. Keep it empty for
questions, policy explanations, hypotheticals, examples, conditional future actions,
or vague help. Multiple explicit same-domain ticket changes may produce multiple
values. Setting the initial status or priority while creating a new ticket belongs to
create_ticket alone; do not also classify it as an update. Use an update intent only
when the user asks to change an already-existing ticket. Return JSON matching the
supplied schema."""


def route_decision_schema() -> dict[str, object]:
    """Make Pydantic's schema compatible with OpenAI strict Structured Outputs."""
    schema = RouteDecision.model_json_schema()
    properties = schema["properties"]
    schema["required"] = list(properties)
    schema["additionalProperties"] = False
    return schema


class OpenAIModelGateway:
    """Production model adapter. It never exposes more than workflow-scoped tools."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def route(self, message: str) -> RouteDecision:
        response = self._create_response(
            operation="routing",
            instructions=ROUTER_INSTRUCTIONS,
            input=[{"role": "user", "content": message}],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "route_decision",
                    "strict": True,
                    "schema": route_decision_schema(),
                }
            },
        )
        try:
            return require_valid_route(RouteDecision.model_validate_json(response.output_text))
        except Exception as exc:  # JSON/model validation is an external boundary.
            logger.warning(
                "OpenAI routing response could not be validated [model=%s, error_type=%s, error=%s]",
                self._model,
                type(exc).__name__,
                exc,
            )
            raise ModelGatewayError(
                "model returned an invalid route decision", operation="routing"
            ) from exc

    def next_workflow_turn(self, request: WorkflowRequest) -> WorkflowTurn:
        instructions = (
            f"You are the {request.route} workflow for a fictional SaaS company. "
            "Use only the tools supplied to you. You may request one or more tools, "
            "or give a concise final answer once the supplied tool results are enough. "
            "Never claim that a proposed write has already happened. Write-proposal tools may "
            "be used only for an explicit, present-tense instruction to create a ticket or "
            "change its status or priority. Never propose an action for an informational, "
            "conditional, hypothetical, or example question. A pending action always requires "
            "a separate human approval; identify that clearly in the answer. For factual "
            "Harborlight claims, use only "
            "the supplied business-tool results and retrieved knowledge sources. Clearly "
            "distinguish customer-specific facts from general knowledge-base guidance. If a "
            "fact is not supported by those sources, say that it cannot be confirmed rather "
            "than inventing a policy or account fact."
        )
        input_items: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": (
                    f"Customer ID: {request.customer_id}\n"
                    f"Customer message: {request.message}\n"
                    f"Previous tool results: {json.dumps([result.model_dump() for result in request.tool_results])}\n"
                    "Retrieved knowledge sources: "
                    f"{json.dumps([source.model_dump() for source in request.knowledge_sources])}"
                ),
            }
        ]
        response = self._create_response(
            operation=f"{request.route}_workflow",
            instructions=instructions,
            input=input_items,
            tools=list(request.tools),
        )
        tool_calls = tuple(
            ToolCall(name=item.name, arguments=json.loads(item.arguments or "{}"))
            for item in response.output
            if getattr(item, "type", None) == "function_call"
        )
        answer = response.output_text.strip() or None
        return WorkflowTurn(tool_calls=tool_calls, answer=answer)

    def _create_response(self, *, operation: str, **kwargs: Any) -> Any:
        try:
            return self._client.responses.create(
                model=self._model,
                store=False,
                parallel_tool_calls=False,
                **kwargs,
            )
        except Exception as exc:  # SDK/network exceptions are mapped at the API boundary.
            logger.exception(
                "OpenAI Responses API request failed [operation=%s, model=%s, error_type=%s, error=%s]",
                operation,
                self._model,
                type(exc).__name__,
                exc,
            )
            raise ModelGatewayError("OpenAI request failed", operation=operation) from exc
