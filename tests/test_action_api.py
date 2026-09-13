from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from service_desk.data.repository import BusinessRepository
from service_desk.main import create_app
from service_desk.ticketing.actions import ActionNotFoundError
from service_desk.ticketing.models import AuditEvent, TicketAction
from tests.fakes import FakeModelGateway


def _action(status: str = "pending") -> TicketAction:
    now = datetime.now(UTC)
    return TicketAction(
        action_id="act_" + "c" * 32,
        customer_id="cus_orbit_001",
        route="support",
        action_type="create_ticket",
        payload={"subject": "API approval test ticket", "category": "support", "priority": "normal"},
        status=status,
        proposed_by_request_id="api-test",
        expires_at=now + timedelta(minutes=30),
        created_at=now,
        updated_at=now,
    )


class StubActionService:
    def __init__(self) -> None:
        self.action = _action()
        self.approvals = 0
        self.rejections = 0

    def get(self, action_id: str, customer_id: str) -> TicketAction:
        if action_id != self.action.action_id or customer_id != self.action.customer_id:
            raise ActionNotFoundError(action_id)
        return self.action

    def audit(self, action_id: str, customer_id: str):
        self.get(action_id, customer_id)
        return (
            AuditEvent(
                event_id=1,
                action_id=action_id,
                event_type="proposed",
                actor_type="model",
                metadata={"action_type": "create_ticket"},
                created_at=self.action.created_at,
            ),
        )

    def approve(self, action_id: str, customer_id: str) -> TicketAction:
        self.get(action_id, customer_id)
        self.approvals += 1
        self.action = self.action.model_copy(update={"status": "succeeded"})
        return self.action

    def reject(self, action_id: str, customer_id: str) -> TicketAction:
        self.get(action_id, customer_id)
        self.rejections += 1
        self.action = self.action.model_copy(update={"status": "rejected"})
        return self.action


def _client(actions: StubActionService) -> TestClient:
    return TestClient(
        create_app(
            model_gateway=FakeModelGateway(),
            repository=BusinessRepository.from_default_seed(),
            action_service=actions,  # type: ignore[arg-type]
        )
    )


def test_action_can_be_inspected_with_sanitized_audit_history() -> None:
    actions = StubActionService()
    response = _client(actions).get(
        f"/api/actions/{actions.action.action_id}", params={"customer_id": "cus_orbit_001"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["approval_required"] is True
    assert payload["audit_events"][0]["event_type"] == "proposed"


def test_action_approval_and_rejection_are_explicit_endpoints() -> None:
    approve_actions = StubActionService()
    approved = _client(approve_actions).post(
        f"/api/actions/{approve_actions.action.action_id}/approve",
        json={"customer_id": "cus_orbit_001"},
    )
    reject_actions = StubActionService()
    rejected = _client(reject_actions).post(
        f"/api/actions/{reject_actions.action.action_id}/reject",
        json={"customer_id": "cus_orbit_001"},
    )

    assert approved.status_code == 200
    assert approved.json()["status"] == "succeeded"
    assert approve_actions.approvals == 1
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert reject_actions.rejections == 1


def test_cross_customer_action_lookup_is_a_non_leaking_404() -> None:
    actions = StubActionService()
    response = _client(actions).get(
        f"/api/actions/{actions.action.action_id}", params={"customer_id": "cus_willow_002"}
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Action was not found for this customer.",
        "code": "action_not_found",
    }
