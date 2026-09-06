from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from service_desk.config import Settings
from service_desk.knowledge import KnowledgeBaseChunker
from service_desk.knowledge.ingestion import KnowledgeIngestor
from service_desk.knowledge.repository import KnowledgeRepository, VECTOR_DIMENSIONS


class DeterministicEmbeddingClient:
    def __init__(self) -> None:
        self.calls = 0

    def embed(
        self, inputs: list[str], *, model: str, dimensions: int
    ) -> tuple[tuple[float, ...], ...]:
        del model
        self.calls += 1
        return tuple(tuple(0.0 for _ in range(dimensions)) for _ in inputs)


@pytest.mark.postgres
def test_unchanged_ingestion_is_idempotent_across_connections() -> None:
    if os.getenv("RUN_POSTGRES_TESTS") != "1":
        pytest.skip("set RUN_POSTGRES_TESTS=1 to run local PostgreSQL integration tests")

    settings = Settings()
    if settings.database_url is None:
        pytest.skip("DATABASE_URL is not configured")

    database_url = settings.database_url.get_secret_value()
    corpus_version = f"test-idempotency-{uuid4().hex}"
    repository_root = Path(__file__).resolve().parents[1]
    chunks = KnowledgeBaseChunker(corpus_version=corpus_version).chunk_directory(
        repository_root / "knowledge", repository_root=repository_root
    )[:2]

    try:
        first_client = DeterministicEmbeddingClient()
        first_repository = KnowledgeRepository.connect(database_url)
        try:
            first_report = KnowledgeIngestor(
                chunker=KnowledgeBaseChunker(corpus_version=corpus_version),
                repository=first_repository,
                embedding_client=first_client,
                embedding_model=settings.openai_embedding_model,
                embedding_dimensions=VECTOR_DIMENSIONS,
                corpus_version=corpus_version,
            ).ingest_chunks(chunks)
        finally:
            first_repository.close()

        second_client = DeterministicEmbeddingClient()
        second_repository = KnowledgeRepository.connect(database_url)
        try:
            second_report = KnowledgeIngestor(
                chunker=KnowledgeBaseChunker(corpus_version=corpus_version),
                repository=second_repository,
                embedding_client=second_client,
                embedding_model=settings.openai_embedding_model,
                embedding_dimensions=VECTOR_DIMENSIONS,
                corpus_version=corpus_version,
            ).ingest_chunks(chunks)
        finally:
            second_repository.close()
    finally:
        cleanup_connection = psycopg.connect(database_url, autocommit=True)
        try:
            cleanup_connection.execute(
                "DELETE FROM knowledge_chunks WHERE corpus_version = %s", (corpus_version,)
            )
        finally:
            cleanup_connection.close()

    assert first_report.embedded == 2
    assert first_client.calls == 1
    assert second_report.embedded == 0
    assert second_report.embedding_api_calls == 0
    assert second_report.unchanged == 2
    assert second_client.calls == 0
