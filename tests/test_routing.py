import pytest

from service_desk.ai.gateway import ModelGatewayError, RouteDecision, require_valid_route


def test_route_decision_allows_explicit_clarification_without_a_route() -> None:
    decision = require_valid_route(
        RouteDecision(needs_clarification=True, rationale="Ambiguous request.")
    )

    assert decision.route is None


def test_route_decision_rejects_a_route_and_clarification_together() -> None:
    with pytest.raises(ModelGatewayError):
        require_valid_route(
            RouteDecision(route="billing", needs_clarification=True, rationale="Invalid.")
        )


def test_route_decision_does_not_apply_a_confidence_threshold() -> None:
    decision = require_valid_route(
        RouteDecision(
            route="technical",
            needs_clarification=False,
            rationale="Explicit technical intent.",
            diagnostic_confidence=0.01,
        )
    )

    assert decision.route == "technical"
