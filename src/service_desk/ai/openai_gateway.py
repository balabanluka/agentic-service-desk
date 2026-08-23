"""OpenAI Responses API implementation of the narrow model gateway."""

import json
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


ROUTER_INSTRUCTIONS = """You route customer-service messages for a fictional SaaS company.
Choose exactly one of support, billing, or technical when the request is clear.
Set needs_clarification to true and route to null when it is ambiguous or combines
unrelated domains. diagnostic_confidence is optional diagnostic metadata only; do
not use it as a threshold. Return JSON matching the supplied schema."""


class OpenAIModelGateway:
    """Production model adapter. It never exposes more than workflow-scoped tools."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def route(self, message: str) -> RouteDecision:
        response = self._create_response(
            instructions=ROUTER_INSTRUCTIONS,
            input_items=[{"role": "user", "content": message}],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "route_decision",
                    "strict": True,
                    "schema": RouteDecision.model_json_schema(),
                }
            },
        )
        try:
            return require_valid_route(RouteDecision.model_validate_json(response.output_text))
        except Exception as exc:  # JSON/model validation is an external boundary.
            raise ModelGatewayError("model returned an invalid route decision") from exc

    def next_workflow_turn(self, request: WorkflowRequest) -> WorkflowTurn:
        instructions = (
            f"You are the {request.route} workflow for a fictional SaaS company. "
            "Use only the tools supplied to you. You may request one or more tools, "
            "or give a concise final answer once the supplied tool results are enough. "
            "Never claim to perform write actions. Do not invent business facts."
        )
        input_items: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": (
                    f"Customer ID: {request.customer_id}\n"
                    f"Customer message: {request.message}\n"
                    f"Previous tool results: {json.dumps([result.model_dump() for result in request.tool_results])}"
                ),
            }
        ]
        response = self._create_response(
            instructions=instructions,
            input_items=input_items,
            tools=list(request.tools),
        )
        tool_calls = tuple(
            ToolCall(name=item.name, arguments=json.loads(item.arguments or "{}"))
            for item in response.output
            if getattr(item, "type", None) == "function_call"
        )
        answer = response.output_text.strip() or None
        return WorkflowTurn(tool_calls=tool_calls, answer=answer)

    def _create_response(self, **kwargs: Any) -> Any:
        try:
            return self._client.responses.create(
                model=self._model,
                store=False,
                parallel_tool_calls=False,
                **kwargs,
            )
        except Exception as exc:  # SDK/network exceptions are mapped at the API boundary.
            raise ModelGatewayError("OpenAI request failed") from exc
