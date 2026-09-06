from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from service_desk.config import Settings
from service_desk.knowledge import KnowledgeBaseChunker
from service_desk.knowledge.repository import EmbeddingRecord, KnowledgeRepository, VECTOR_DIMENSIONS
from service_desk.knowledge.retrieval import KnowledgeRetriever


class QueryEmbeddingClient:
    def __init__(self, vector: tuple[float, ...]) -> None:
        self.vector = vector
        self.calls = 0

    def embed(
        self, inputs: tuple[str, ...], *, model: str, dimensions: int
    ) -> tuple[tuple[float, ...], ...]:
        del inputs, model, dimensions
        self.calls += 1
        return (self.vector,)


def _vector(position: int) -> tuple[float, ...]:
    return tuple(1.0 if index == position else 0.0 for index in range(VECTOR_DIMENSIONS))


@pytest.mark.postgres
def test_exact_cosine_retrieval_filters_active_chunks_models_and_domains() -> None:
    if os.getenv("RUN_POSTGRES_TESTS") != "1":
        pytest.skip("set RUN_POSTGRES_TESTS=1 to run local PostgreSQL integration tests")

    settings = Settings()
    if settings.database_url is None:
        pytest.skip("DATABASE_URL is not configured")

    database_url = settings.database_url.get_secret_value()
    corpus_version = f"test-retrieval-{uuid4().hex}"
    root = Path(__file__).resolve().parents[1]
    source_chunks = KnowledgeBaseChunker(corpus_version=corpus_version).chunk_directory(
        root / "knowledge", repository_root=root
    )
    billing = next(chunk for chunk in source_chunks if chunk.domain == "billing")
    technical = next(chunk for chunk in source_chunks if chunk.domain == "technical")
    inactive_support = next(chunk for chunk in source_chunks if chunk.domain == "support")
    chunks = (billing, technical, inactive_support)
    primary_model = "test-embedding-1536"
    embeddings = (
        EmbeddingRecord(
            corpus_version=corpus_version,
            chunk_id=billing.chunk_id,
            embedding_model=primary_model,
            embedding_dimensions=VECTOR_DIMENSIONS,
            embedding_content_sha256=billing.content_sha256,
            embedding=_vector(0),
        ),
        EmbeddingRecord(
            corpus_version=corpus_version,
            chunk_id=technical.chunk_id,
            embedding_model=primary_model,
            embedding_dimensions=VECTOR_DIMENSIONS,
            embedding_content_sha256=technical.content_sha256,
            embedding=_vector(1),
        ),
        EmbeddingRecord(
            corpus_version=corpus_version,
            chunk_id=inactive_support.chunk_id,
            embedding_model=primary_model,
            embedding_dimensions=VECTOR_DIMENSIONS,
            embedding_content_sha256=inactive_support.content_sha256,
            embedding=_vector(0),
        ),
        EmbeddingRecord(
            corpus_version=corpus_version,
            chunk_id=billing.chunk_id,
            embedding_model="other-model",
            embedding_dimensions=VECTOR_DIMENSIONS,
            embedding_content_sha256=billing.content_sha256,
            embedding=_vector(1),
        ),
    )

    repository = KnowledgeRepository.connect(database_url)
    try:
        with repository.transaction():
            repository.upsert_chunks(chunks)
            repository.upsert_embeddings(embeddings)
            repository.retire_missing_chunks(corpus_version, (billing.chunk_id, technical.chunk_id))

        client = QueryEmbeddingClient(_vector(0))
        retriever = KnowledgeRetriever(
            repository=repository,
            embedding_client=client,
            embedding_model=primary_model,
            embedding_dimensions=VECTOR_DIMENSIONS,
            corpus_version=corpus_version,
        )
        all_results = retriever.search("synthetic query")
        technical_results = retriever.search("synthetic query", domain="technical")
    finally:
        repository.close()
        cleanup_connection = psycopg.connect(database_url, autocommit=True)
        try:
            cleanup_connection.execute(
                "DELETE FROM knowledge_chunks WHERE corpus_version = %s", (corpus_version,)
            )
        finally:
            cleanup_connection.close()

    assert [result.chunk_id for result in all_results] == [billing.chunk_id, technical.chunk_id]
    assert all_results[0].cosine_distance == pytest.approx(0.0)
    assert all_results[0].cosine_similarity == pytest.approx(1.0)
    assert [result.chunk_id for result in technical_results] == [technical.chunk_id]
    assert client.calls == 2
