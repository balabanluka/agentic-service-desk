from fastapi.testclient import TestClient

from service_desk.ai.gateway import ModelGatewayError
from service_desk.config import Settings
from service_desk.data.repository import BusinessRepository
from service_desk.knowledge.retrieval import KnowledgeSearchResult
from service_desk.main import create_app
from tests.fakes import FakeModelGateway


class StaticKnowledgeRetriever:
    def search(self, query: str, *, domain: str | None = None, top_k: int | None = None):
        del query, domain, top_k
        return (
            KnowledgeSearchResult(
                rank=1,
                chunk_id="KB-TECHNICAL-001--chunk-v1--001",
                chunking_version="v1",
                corpus_version="kb-v1",
                document_id="KB-TECHNICAL-001",
                document_title="Technical guidance",
                domain="technical",
                product="Harborlight Cloud",
                heading_path=("Technical guidance",),
                included_heading_paths=(("Technical guidance",),),
                chunk_index=1,
                source_path="knowledge/technical/guidance.md",
                content="Synthetic technical guidance.",
                word_count=3,
                content_sha256="a" * 64,
                source_commit="b" * 40,
                cosine_distance=0.1,
                cosine_similarity=0.9,
            ),
        )


def test_health_is_available_without_an_openai_key() -> None:
    response = TestClient(create_app(settings=Settings(_env_file=None))).get("/health")

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


def test_chat_exposes_concise_knowledge_source_metadata_only() -> None:
    response = TestClient(
        create_app(
            model_gateway=FakeModelGateway(route="technical"),
            repository=BusinessRepository.from_default_seed(),
            knowledge_retriever=StaticKnowledgeRetriever(),
        )
    ).post(
        "/api/chat",
        json={"customer_id": "cus_orbit_001", "message": "Why does my CSV export time out?"},
    )

    assert response.status_code == 200
    sources = response.json()["execution"]["knowledge_sources"]
    assert sources == [
        {
            "document_id": "KB-TECHNICAL-001",
            "document_title": "Technical guidance",
            "chunk_id": "KB-TECHNICAL-001--chunk-v1--001",
            "source_path": "knowledge/technical/guidance.md",
        }
    ]
    assert "content" not in sources[0]
