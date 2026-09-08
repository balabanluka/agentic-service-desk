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


ROUTER_INSTRUCTIONS = """You route customer-service messages for a fictional SaaS company.
Choose exactly one of support, billing, or technical when the request is clear.
Set needs_clarification to true and route to null when it is ambiguous or combines
unrelated domains. diagnostic_confidence is optional diagnostic metadata only; do
not use it as a threshold. Set diagnostic_confidence to null when it is unavailable.
Return JSON matching the supplied schema."""


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
            "Never claim to perform write actions. For factual Harborlight claims, use only "
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
