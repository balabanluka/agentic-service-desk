from fastapi.testclient import TestClient

from service_desk.ai.gateway import ModelGatewayError
from service_desk.data.repository import BusinessRepository
from service_desk.main import create_app
from tests.fakes import FakeModelGateway


def test_health_is_available_without_an_openai_key() -> None:
    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_returns_answer_and_execution_metadata(client: TestClient) -> None:
    response = client.post(
        "/api/chat",
        json={"customer_id": "cus_orbit_001", "message": "Why was I billed?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"].startswith("Offline billing answer")
    assert payload["execution"]["selected_route"] == "billing"
    assert payload["execution"]["tools_used"] == ["get_customer", "get_subscription"]
    assert payload["execution"]["graph_path"] == [
        "load_customer",
        "route_request",
        "billing_workflow",
    ]


def test_chat_rejects_missing_customer_id(client: TestClient) -> None:
    response = client.post("/api/chat", json={"message": "Why was I billed?"})

    assert response.status_code == 422


def test_chat_returns_404_for_unknown_customer(client: TestClient) -> None:
    response = client.post(
        "/api/chat",
        json={"customer_id": "cus_unknown_999", "message": "Help"},
    )

    assert response.status_code == 404
    assert response.headers["X-Error-Code"] == "customer_not_found"
    assert response.json()["code"] == "customer_not_found"


class FailingGateway(FakeModelGateway):
    def route(self, message: str):
        raise ModelGatewayError("offline failure")


def test_chat_returns_503_when_the_model_gateway_fails() -> None:
    client = TestClient(
        create_app(
            model_gateway=FailingGateway(),
            repository=BusinessRepository.from_default_seed(),
        )
    )

    response = client.post(
        "/api/chat",
        json={"customer_id": "cus_orbit_001", "message": "Help"},
    )

    assert response.status_code == 503
    assert response.headers["X-Error-Code"] == "model_unavailable"
    assert response.json()["code"] == "model_unavailable"
