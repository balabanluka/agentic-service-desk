import pytest
from fastapi.testclient import TestClient

from service_desk.data.repository import BusinessRepository
from service_desk.main import create_app
from tests.fakes import FakeModelGateway


@pytest.fixture(autouse=True)
def no_openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests always inject a fake gateway and must never use a live key."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)


@pytest.fixture
def fake_gateway() -> FakeModelGateway:
    return FakeModelGateway(route="billing")


@pytest.fixture
def client(fake_gateway: FakeModelGateway) -> TestClient:
    return TestClient(
        create_app(
            model_gateway=fake_gateway,
            repository=BusinessRepository.from_default_seed(),
        )
    )
