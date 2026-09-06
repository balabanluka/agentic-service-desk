from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from service_desk.knowledge import KnowledgeBaseChunker, KnowledgeChunk
from service_desk.knowledge.embeddings import EmbeddingClientError
from service_desk.knowledge.ingestion import KnowledgeIngestionError, KnowledgeIngestor
from service_desk.knowledge.repository import (
    VECTOR_DIMENSIONS,
    EmbeddingRecord,
    ExistingChunk,
    ExistingEmbedding,
)


class DeterministicEmbeddingClient:
    def __init__(self, *, dimensions: int = VECTOR_DIMENSIONS, fail: bool = False) -> None:
        self.dimensions = dimensions
        self.fail = fail
        self.calls: list[tuple[tuple[str, ...], str, int]] = []

    def embed(
        self, inputs: Sequence[str], *, model: str, dimensions: int
    ) -> tuple[tuple[float, ...], ...]:
        self.calls.append((tuple(inputs), model, dimensions))
        if self.fail:
            raise EmbeddingClientError("offline embedding failure")
        return tuple(
            tuple(float(index + input_index) for index in range(self.dimensions))
            for input_index, _ in enumerate(inputs)
        )


class InMemoryKnowledgeRepository:
    def __init__(self) -> None:
        self.chunks: dict[str, ExistingChunk] = {}
        self.embeddings: dict[tuple[str, str], ExistingEmbedding] = {}
        self.transaction_calls = 0

    @contextmanager
    def transaction(self) -> Iterator["InMemoryKnowledgeRepository"]:
        self.transaction_calls += 1
        chunk_snapshot = dict(self.chunks)
        embedding_snapshot = dict(self.embeddings)
        try:
            yield self
        except Exception:
            self.chunks = chunk_snapshot
            self.embeddings = embedding_snapshot
            raise

    def existing_chunks(self, _: str) -> dict[str, ExistingChunk]:
        return dict(self.chunks)

    def existing_embedding_fingerprints(
        self, _: str, embedding_model: str
    ) -> dict[str, ExistingEmbedding]:
        return {
            chunk_id: embedding
            for (chunk_id, model), embedding in self.embeddings.items()
            if model == embedding_model
        }

    def upsert_chunks(self, chunks: Sequence[KnowledgeChunk]) -> int:
        for chunk in chunks:
            self.chunks[chunk.chunk_id] = ExistingChunk(chunk.content_sha256, True)
        return len(chunks)

    def upsert_embeddings(self, embeddings: Sequence[EmbeddingRecord]) -> int:
        for embedding in embeddings:
            self.embeddings[(embedding.chunk_id, embedding.embedding_model)] = ExistingEmbedding(
                embedding.embedding_content_sha256, embedding.embedding_dimensions
            )
        return len(embeddings)

    def retire_missing_chunks(self, _: str, current_chunk_ids: Sequence[str]) -> int:
        retired = 0
        current = set(current_chunk_ids)
        for chunk_id, chunk in tuple(self.chunks.items()):
            if chunk_id not in current and chunk.is_active:
                self.chunks[chunk_id] = ExistingChunk(chunk.content_sha256, False)
                retired += 1
        return retired


def _chunks() -> tuple[KnowledgeChunk, ...]:
    root = Path(__file__).resolve().parents[1]
    return KnowledgeBaseChunker().chunk_directory(root / "knowledge", repository_root=root)[:2]


def _ingestor(
    repository: InMemoryKnowledgeRepository,
    client: DeterministicEmbeddingClient,
    *,
    model: str = "text-embedding-3-small",
) -> KnowledgeIngestor:
    return KnowledgeIngestor(
        chunker=KnowledgeBaseChunker(),
        repository=repository,  # type: ignore[arg-type]
        embedding_client=client,
        embedding_model=model,
        embedding_dimensions=VECTOR_DIMENSIONS,
        corpus_version="kb-v1",
    )


def test_initial_ingestion_and_unchanged_rerun_are_idempotent() -> None:
    repository = InMemoryKnowledgeRepository()
    client = DeterministicEmbeddingClient()
    ingestor = _ingestor(repository, client)
    chunks = _chunks()

    initial = ingestor.ingest_chunks(chunks)
    rerun = ingestor.ingest_chunks(chunks)

    assert initial.chunks_seen == 2
    assert initial.embedded == 2
    assert initial.unchanged == 0
    assert initial.updated == 2
    assert initial.retired == 0
    assert initial.embedding_api_calls == 1
    assert rerun.embedded == 0
    assert rerun.unchanged == 2
    assert rerun.updated == 0
    assert rerun.embedding_api_calls == 0
    assert len(client.calls) == 1


def test_changed_content_reembeds_only_the_changed_chunk() -> None:
    repository = InMemoryKnowledgeRepository()
    client = DeterministicEmbeddingClient()
    ingestor = _ingestor(repository, client)
    chunks = _chunks()
    ingestor.ingest_chunks(chunks)
    changed_content = chunks[0].content + "\nChanged synthetic wording.\n"
    changed = replace(
        chunks[0],
        content=changed_content,
        content_sha256=sha256(changed_content.encode("utf-8")).hexdigest(),
    )

    report = ingestor.ingest_chunks((changed, chunks[1]))

    assert report.embedded == 1
    assert report.unchanged == 1
    assert report.updated == 1
    assert report.embedding_api_calls == 1
    assert client.calls[-1][0] == (changed.content,)


def test_model_change_creates_a_new_embedding_profile_without_rewriting_chunks() -> None:
    repository = InMemoryKnowledgeRepository()
    client = DeterministicEmbeddingClient()
    chunks = _chunks()
    _ingestor(repository, client).ingest_chunks(chunks)

    report = _ingestor(repository, client, model="another-1536-model").ingest_chunks(chunks)

    assert report.embedding_model == "another-1536-model"
    assert report.embedded == 2
    assert report.unchanged == 0
    assert report.updated == 0
    assert len(repository.embeddings) == 4


def test_wrong_vector_dimension_fails_before_the_transaction() -> None:
    repository = InMemoryKnowledgeRepository()
    client = DeterministicEmbeddingClient(dimensions=3)

    with pytest.raises(KnowledgeIngestionError, match="does not match"):
        _ingestor(repository, client).ingest_chunks(_chunks())

    assert repository.transaction_calls == 0
    assert not repository.chunks


def test_retirement_and_embedding_failure_leave_safe_state() -> None:
    repository = InMemoryKnowledgeRepository()
    repository.chunks["retired-chunk"] = ExistingChunk("stale", True)
    client = DeterministicEmbeddingClient()

    report = _ingestor(repository, client).ingest_chunks(_chunks())

    assert report.retired == 1
    assert repository.chunks["retired-chunk"].is_active is False

    failing_repository = InMemoryKnowledgeRepository()
    previous_chunk = _chunks()[0]
    failing_repository.chunks[previous_chunk.chunk_id] = ExistingChunk(
        previous_chunk.content_sha256, True
    )
    failing_client = DeterministicEmbeddingClient(fail=True)
    with pytest.raises(EmbeddingClientError, match="offline embedding failure"):
        _ingestor(failing_repository, failing_client).ingest_chunks(_chunks())
    assert failing_repository.transaction_calls == 0
    assert failing_repository.chunks == {
        previous_chunk.chunk_id: ExistingChunk(previous_chunk.content_sha256, True)
    }
