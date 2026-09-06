from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pytest

from service_desk.knowledge import KnowledgeBaseChunker
from service_desk.knowledge.repository import EmbeddingRecord, KnowledgeRepository, VECTOR_DIMENSIONS


class RecordingCursor:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.calls: list[tuple[str, object]] = []
        self.executemany_calls: list[tuple[str, list[object]]] = []
        self._rows = rows or []
        self.rowcount = 3

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: str, params: object = None) -> None:
        self.calls.append((query, params))

    def executemany(self, query: str, params_seq: list[object]) -> None:
        self.executemany_calls.append((query, params_seq))

    def fetchall(self) -> list[dict[str, object]]:
        return self._rows


class RecordingConnection:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.cursor_instance = RecordingCursor(rows)
        self.closed = False

    def cursor(self, **_: object) -> RecordingCursor:
        return self.cursor_instance

    @contextmanager
    def transaction(self) -> Iterator[None]:
        yield

    def close(self) -> None:
        self.closed = True


def test_repository_reads_existing_fingerprints_without_an_embedding_client() -> None:
    chunk_connection = RecordingConnection(
        [{"chunk_id": "chunk-1", "content_sha256": "a" * 64, "is_active": True}]
    )
    repository = KnowledgeRepository(chunk_connection)  # type: ignore[arg-type]

    chunks = repository.existing_chunks("kb-v1")

    assert chunks["chunk-1"].content_sha256 == "a" * 64
    assert chunks["chunk-1"].is_active is True
    assert chunk_connection.cursor_instance.calls[0][1] == ("kb-v1",)

    embedding_connection = RecordingConnection(
        [
            {
                "chunk_id": "chunk-1",
                "embedding_content_sha256": "b" * 64,
                "embedding_dimensions": VECTOR_DIMENSIONS,
            }
        ]
    )
    repository = KnowledgeRepository(embedding_connection)  # type: ignore[arg-type]
    embeddings = repository.existing_embedding_fingerprints("kb-v1", "text-embedding-3-small")

    assert embeddings["chunk-1"].embedding_dimensions == VECTOR_DIMENSIONS
    assert embedding_connection.cursor_instance.calls[0][1] == (
        "kb-v1",
        "text-embedding-3-small",
    )


def test_repository_upserts_chunks_and_refuses_empty_retirement() -> None:
    root = Path(__file__).resolve().parents[1]
    chunk = KnowledgeBaseChunker().chunk_directory(root / "knowledge", repository_root=root)[0]
    connection = RecordingConnection()
    repository = KnowledgeRepository(connection)  # type: ignore[arg-type]

    assert repository.upsert_chunks((chunk,)) == 1
    assert "ON CONFLICT (corpus_version, chunk_id)" in connection.cursor_instance.executemany_calls[0][0]
    with pytest.raises(ValueError, match="empty corpus"):
        repository.retire_missing_chunks("kb-v1", ())

    assert repository.retire_missing_chunks("kb-v1", (chunk.chunk_id,)) == 3
    assert "is_active = false" in connection.cursor_instance.calls[0][0]


def test_embedding_records_validate_dimensions_and_unique_keys() -> None:
    vector = tuple(0.0 for _ in range(VECTOR_DIMENSIONS))
    record = EmbeddingRecord(
        corpus_version="kb-v1",
        chunk_id="KB-BIL-001--chunk-v1--001",
        embedding_model="text-embedding-3-small",
        embedding_dimensions=VECTOR_DIMENSIONS,
        embedding_content_sha256="a" * 64,
        embedding=vector,
    )
    connection = RecordingConnection()
    repository = KnowledgeRepository(connection)  # type: ignore[arg-type]

    assert repository.upsert_embeddings((record,)) == 1
    with pytest.raises(ValueError, match="unique corpus"):
        repository.upsert_embeddings((record, record))
    with pytest.raises(ValueError, match="embedding_dimensions"):
        EmbeddingRecord(
            corpus_version="kb-v1",
            chunk_id="other",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=3,
            embedding_content_sha256="b" * 64,
            embedding=(0.0, 0.0, 0.0),
        )
