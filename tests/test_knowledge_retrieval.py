from __future__ import annotations

from collections.abc import Sequence

import pytest

from service_desk.knowledge.repository import RetrievedKnowledgeChunk, VECTOR_DIMENSIONS
from service_desk.knowledge.retrieval import (
    KnowledgeRetrievalError,
    KnowledgeRetriever,
)


class RecordingEmbeddingClient:
    def __init__(self, vector: tuple[float, ...] | None = None) -> None:
        self.vector = vector or tuple(0.0 for _ in range(VECTOR_DIMENSIONS))
        self.calls: list[tuple[tuple[str, ...], str, int]] = []

    def embed(
        self, inputs: Sequence[str], *, model: str, dimensions: int
    ) -> tuple[tuple[float, ...], ...]:
        self.calls.append((tuple(inputs), model, dimensions))
        return (self.vector,)


class RecordingRepository:
    def __init__(self, matches: tuple[RetrievedKnowledgeChunk, ...]) -> None:
        self.matches = matches
        self.calls: list[dict[str, object]] = []

    def search_active_chunks(self, **kwargs: object) -> tuple[RetrievedKnowledgeChunk, ...]:
        self.calls.append(kwargs)
        return self.matches


def _match(*, chunk_id: str, distance: float) -> RetrievedKnowledgeChunk:
    return RetrievedKnowledgeChunk(
        chunk_id=chunk_id,
        chunking_version="v1",
        corpus_version="kb-v1",
        document_id="KB-TEC-003",
        document_title="CSV Export Limits",
        domain="technical",
        product="Harborlight Cloud",
        heading_path=("CSV Export Limits", "Timeouts"),
        included_heading_paths=(("CSV Export Limits", "Timeouts"),),
        chunk_index=1,
        source_path="knowledge/technical/csv-export-limits.md",
        content="Synthetic chunk content.",
        word_count=3,
        content_sha256="a" * 64,
        source_commit="b" * 40,
        cosine_distance=distance,
    )


def _retriever(
    repository: RecordingRepository,
    client: RecordingEmbeddingClient,
    *,
    default_top_k: int = 4,
) -> KnowledgeRetriever:
    return KnowledgeRetriever(
        repository=repository,  # type: ignore[arg-type]
        embedding_client=client,
        embedding_model="text-embedding-3-small",
        embedding_dimensions=VECTOR_DIMENSIONS,
        corpus_version="kb-v1",
        default_top_k=default_top_k,
    )


def test_retriever_embeds_each_query_and_returns_ranked_similarity_metadata() -> None:
    repository = RecordingRepository((_match(chunk_id="first", distance=0.1), _match(chunk_id="second", distance=0.4)))
    client = RecordingEmbeddingClient()

    results = _retriever(repository, client).search(
        "  Why do CSV exports time out?  ", domain="technical"
    )

    assert client.calls == [
        (("Why do CSV exports time out?",), "text-embedding-3-small", VECTOR_DIMENSIONS)
    ]
    assert repository.calls == [
        {
            "corpus_version": "kb-v1",
            "embedding_model": "text-embedding-3-small",
            "query_embedding": client.vector,
            "domain": "technical",
            "top_k": 4,
        }
    ]
    assert [result.rank for result in results] == [1, 2]
    assert results[0].cosine_similarity == pytest.approx(0.9)
    assert results[1].cosine_similarity == pytest.approx(0.6)
    assert results[0].as_dict()["heading_path"] == ["CSV Export Limits", "Timeouts"]


@pytest.mark.parametrize("query", ["", " \n\t "])
def test_retriever_rejects_blank_queries_before_embedding(query: str) -> None:
    repository = RecordingRepository(())
    client = RecordingEmbeddingClient()

    with pytest.raises(KnowledgeRetrievalError, match="blank"):
        _retriever(repository, client).search(query)

    assert not client.calls
    assert not repository.calls


@pytest.mark.parametrize("domain", ["", "sales", "Technical"])
def test_retriever_rejects_invalid_domains_before_embedding(domain: str) -> None:
    repository = RecordingRepository(())
    client = RecordingEmbeddingClient()

    with pytest.raises(KnowledgeRetrievalError, match="domain"):
        _retriever(repository, client).search("find policy", domain=domain)

    assert not client.calls


@pytest.mark.parametrize("top_k", [0, 11, True])
def test_retriever_validates_top_k_before_embedding(top_k: int) -> None:
    repository = RecordingRepository(())
    client = RecordingEmbeddingClient()

    with pytest.raises(KnowledgeRetrievalError, match="top_k"):
        _retriever(repository, client).search("find policy", top_k=top_k)

    assert not client.calls


def test_retriever_rejects_wrong_dimension_before_search() -> None:
    repository = RecordingRepository(())
    client = RecordingEmbeddingClient((0.0, 1.0))

    with pytest.raises(KnowledgeRetrievalError, match="dimension"):
        _retriever(repository, client).search("find policy")

    assert not repository.calls
