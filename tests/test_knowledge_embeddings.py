from __future__ import annotations

from types import SimpleNamespace

import pytest

from service_desk.knowledge.embeddings import EmbeddingClientError, OpenAIEmbeddingClient


class RecordingEmbeddingsAPI:
    def __init__(self, response: object | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def test_openai_embedding_client_uses_configured_batch_shape(monkeypatch) -> None:
    api = RecordingEmbeddingsAPI(
        SimpleNamespace(
            data=[
                SimpleNamespace(index=1, embedding=[0.2, 0.3]),
                SimpleNamespace(index=0, embedding=[0.0, 0.1]),
            ]
        )
    )
    client = OpenAIEmbeddingClient("test-key")
    monkeypatch.setattr(client, "_client", SimpleNamespace(embeddings=api))

    vectors = client.embed(("first", "second"), model="test-embedding", dimensions=2)

    assert vectors == ((0.0, 0.1), (0.2, 0.3))
    assert api.calls == [
        {
            "model": "test-embedding",
            "input": ["first", "second"],
            "dimensions": 2,
            "encoding_format": "float",
        }
    ]


def test_openai_embedding_client_maps_provider_errors_without_calling_network(monkeypatch) -> None:
    api = RecordingEmbeddingsAPI(error=RuntimeError("offline provider failure"))
    client = OpenAIEmbeddingClient("test-key")
    monkeypatch.setattr(client, "_client", SimpleNamespace(embeddings=api))

    with pytest.raises(EmbeddingClientError, match="embeddings request failed"):
        client.embed(("first",), model="test-embedding", dimensions=2)
