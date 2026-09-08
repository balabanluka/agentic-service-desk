from types import SimpleNamespace

from service_desk.ai.gateway import KnowledgeSource, WorkflowRequest
from service_desk.ai.openai_gateway import OpenAIModelGateway, route_decision_schema


class FakeResponses:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.response


def test_openai_gateway_parses_structured_route_without_network() -> None:
    responses = FakeResponses(
        SimpleNamespace(
            output_text=(
                '{"route":"billing","needs_clarification":false,'
                '"rationale":"Payment question."}'
            )
        )
    )
    gateway = OpenAIModelGateway("test-key", "test-model")
    gateway._client = SimpleNamespace(responses=responses)  # type: ignore[assignment]

    decision = gateway.route("Why was I billed?")

    assert decision.route == "billing"
    assert responses.calls[0]["store"] is False
    assert responses.calls[0]["text"] is not None
    assert responses.calls[0]["input"] == [{"role": "user", "content": "Why was I billed?"}]
    assert "input_items" not in responses.calls[0]


def test_openai_gateway_reads_function_calls_from_a_scoped_response() -> None:
    responses = FakeResponses(
        SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="function_call", name="get_subscription", arguments="{}"
                )
            ],
            output_text="",
        )
    )
    gateway = OpenAIModelGateway("test-key", "test-model")
    gateway._client = SimpleNamespace(responses=responses)  # type: ignore[assignment]
    request = WorkflowRequest(
        route="billing",
        customer_id="cus_orbit_001",
        message="Why was I billed?",
        tools=(
            {
                "type": "function",
                "name": "get_subscription",
                "description": "Get subscription.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                "strict": True,
            },
        ),
        knowledge_sources=(
            KnowledgeSource(
                document_id="KB-BIL-001",
                document_title="Billing cycles",
                chunk_id="KB-BIL-001--chunk-v1--001",
                source_path="knowledge/billing/billing-cycles.md",
                content="Synthetic billing guidance.",
            ),
        ),
    )

    turn = gateway.next_workflow_turn(request)

    assert turn.tool_calls[0].name == "get_subscription"
    assert responses.calls[0]["tools"] == list(request.tools)
    assert responses.calls[0]["parallel_tool_calls"] is False
    assert "input" in responses.calls[0]
    assert "input_items" not in responses.calls[0]
    assert "Synthetic billing guidance." in responses.calls[0]["input"][0]["content"]


def test_openai_gateway_sends_an_empty_tool_list_for_answer_only_synthesis() -> None:
    responses = FakeResponses(SimpleNamespace(output=[], output_text="Grounded final answer."))
    gateway = OpenAIModelGateway("test-key", "test-model")
    gateway._client = SimpleNamespace(responses=responses)  # type: ignore[assignment]
    request = WorkflowRequest(
        route="billing",
        customer_id="cus_willow_002",
        message="Why is the invoice past due?",
        tools=(),
    )

    turn = gateway.next_workflow_turn(request)

    assert turn.answer == "Grounded final answer."
    assert responses.calls[0]["tools"] == []


def test_route_schema_is_compatible_with_strict_structured_outputs() -> None:
    schema = route_decision_schema()

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
