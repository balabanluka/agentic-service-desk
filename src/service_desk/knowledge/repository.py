"""Direct psycopg persistence primitives for future knowledge ingestion."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Self

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from service_desk.knowledge.chunking import KnowledgeChunk


VECTOR_DIMENSIONS = 1536


@dataclass(frozen=True, slots=True)
class ExistingChunk:
    content_sha256: str
    is_active: bool


@dataclass(frozen=True, slots=True)
class ExistingEmbedding:
    embedding_content_sha256: str
    embedding_dimensions: int


@dataclass(frozen=True, slots=True)
class EmbeddingRecord:
    """A validated embedding value supplied by a future embedding gateway."""

    corpus_version: str
    chunk_id: str
    embedding_model: str
    embedding_dimensions: int
    embedding_content_sha256: str
    embedding: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.embedding_model:
            raise ValueError("embedding_model must not be empty")
        if self.embedding_dimensions != VECTOR_DIMENSIONS:
            raise ValueError(f"embedding_dimensions must be {VECTOR_DIMENSIONS}")
        if len(self.embedding) != self.embedding_dimensions:
            raise ValueError("embedding length does not match embedding_dimensions")


class KnowledgeRepository:
    """Database operations for chunk and embedding lifecycle management only."""

    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    @classmethod
    def connect(cls, database_url: str) -> Self:
        # Reads performed before an explicit ingestion transaction must not leave an
        # implicit outer transaction open. In autocommit mode, ``transaction()``
        # below always creates the real commit/rollback boundary for a write unit.
        connection = psycopg.connect(database_url, autocommit=True)
        register_vector(connection)
        return cls(connection)

    def close(self) -> None:
        self._connection.close()

    @contextmanager
    def transaction(self) -> Iterator[Self]:
        """Expose an explicit transaction boundary to future ingestion code."""

        with self._connection.transaction():
            yield self

    def existing_chunks(self, corpus_version: str) -> dict[str, ExistingChunk]:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT chunk_id, content_sha256, is_active
                FROM knowledge_chunks
                WHERE corpus_version = %s
                """,
                (corpus_version,),
            )
            return {
                str(row["chunk_id"]): ExistingChunk(
                    content_sha256=str(row["content_sha256"]),
                    is_active=bool(row["is_active"]),
                )
                for row in cursor.fetchall()
            }

    def existing_embedding_fingerprints(
        self, corpus_version: str, embedding_model: str
    ) -> dict[str, ExistingEmbedding]:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT chunk_id, embedding_content_sha256, embedding_dimensions
                FROM knowledge_embeddings
                WHERE corpus_version = %s AND embedding_model = %s
                """,
                (corpus_version, embedding_model),
            )
            return {
                str(row["chunk_id"]): ExistingEmbedding(
                    embedding_content_sha256=str(row["embedding_content_sha256"]),
                    embedding_dimensions=int(row["embedding_dimensions"]),
                )
                for row in cursor.fetchall()
            }

    def upsert_chunks(self, chunks: Sequence[KnowledgeChunk]) -> int:
        """Insert or refresh current chunks without changing unchanged rows."""

        _ensure_unique_chunk_keys(chunks)
        if not chunks:
            return 0
        records = [
            (
                chunk.corpus_version,
                chunk.chunk_id,
                chunk.chunking_version,
                chunk.document_id,
                chunk.document_title,
                chunk.domain,
                chunk.product,
                Jsonb(list(chunk.heading_path)),
                Jsonb([list(path) for path in chunk.included_heading_paths]),
                chunk.chunk_index,
                chunk.source_path,
                chunk.content,
                chunk.word_count,
                chunk.content_sha256,
                chunk.source_commit,
            )
            for chunk in chunks
        ]
        with self._connection.cursor() as cursor:
            cursor.executemany(_UPSERT_CHUNK_SQL, records)
        return len(records)

    def upsert_embeddings(self, embeddings: Sequence[EmbeddingRecord]) -> int:
        """Insert or replace embeddings for a model-specific chunk identity."""

        _ensure_unique_embedding_keys(embeddings)
        if not embeddings:
            return 0
        records = [
            (
                embedding.corpus_version,
                embedding.chunk_id,
                embedding.embedding_model,
                embedding.embedding_dimensions,
                embedding.embedding_content_sha256,
                list(embedding.embedding),
            )
            for embedding in embeddings
        ]
        with self._connection.cursor() as cursor:
            cursor.executemany(_UPSERT_EMBEDDING_SQL, records)
        return len(records)

    def retire_missing_chunks(self, corpus_version: str, current_chunk_ids: Sequence[str]) -> int:
        """Soft-retire active chunks absent from a validated current corpus."""

        if not current_chunk_ids:
            raise ValueError("refusing to retire chunks from an empty corpus")
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE knowledge_chunks
                SET is_active = false, retired_at = now(), updated_at = now()
                WHERE corpus_version = %s
                  AND is_active = true
                  AND NOT (chunk_id = ANY(%s))
                """,
                (corpus_version, list(current_chunk_ids)),
            )
            return cursor.rowcount


_UPSERT_CHUNK_SQL = """
INSERT INTO knowledge_chunks AS existing (
    corpus_version, chunk_id, chunking_version, document_id, document_title,
    domain, product, heading_path, included_heading_paths, chunk_index,
    source_path, content, word_count, content_sha256, source_commit
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
)
ON CONFLICT (corpus_version, chunk_id) DO UPDATE SET
    chunking_version = EXCLUDED.chunking_version,
    document_id = EXCLUDED.document_id,
    document_title = EXCLUDED.document_title,
    domain = EXCLUDED.domain,
    product = EXCLUDED.product,
    heading_path = EXCLUDED.heading_path,
    included_heading_paths = EXCLUDED.included_heading_paths,
    chunk_index = EXCLUDED.chunk_index,
    source_path = EXCLUDED.source_path,
    content = EXCLUDED.content,
    word_count = EXCLUDED.word_count,
    content_sha256 = EXCLUDED.content_sha256,
    source_commit = EXCLUDED.source_commit,
    is_active = true,
    retired_at = NULL,
    updated_at = now()
WHERE
    existing.chunking_version IS DISTINCT FROM EXCLUDED.chunking_version
    OR existing.document_id IS DISTINCT FROM EXCLUDED.document_id
    OR existing.document_title IS DISTINCT FROM EXCLUDED.document_title
    OR existing.domain IS DISTINCT FROM EXCLUDED.domain
    OR existing.product IS DISTINCT FROM EXCLUDED.product
    OR existing.heading_path IS DISTINCT FROM EXCLUDED.heading_path
    OR existing.included_heading_paths IS DISTINCT FROM EXCLUDED.included_heading_paths
    OR existing.chunk_index IS DISTINCT FROM EXCLUDED.chunk_index
    OR existing.source_path IS DISTINCT FROM EXCLUDED.source_path
    OR existing.content IS DISTINCT FROM EXCLUDED.content
    OR existing.word_count IS DISTINCT FROM EXCLUDED.word_count
    OR existing.content_sha256 IS DISTINCT FROM EXCLUDED.content_sha256
    OR existing.source_commit IS DISTINCT FROM EXCLUDED.source_commit
    OR existing.is_active IS DISTINCT FROM true
"""

_UPSERT_EMBEDDING_SQL = """
INSERT INTO knowledge_embeddings AS existing (
    corpus_version, chunk_id, embedding_model, embedding_dimensions,
    embedding_content_sha256, embedding
) VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (corpus_version, chunk_id, embedding_model) DO UPDATE SET
    embedding_dimensions = EXCLUDED.embedding_dimensions,
    embedding_content_sha256 = EXCLUDED.embedding_content_sha256,
    embedding = EXCLUDED.embedding,
    embedded_at = now()
WHERE
    existing.embedding_dimensions IS DISTINCT FROM EXCLUDED.embedding_dimensions
    OR existing.embedding_content_sha256 IS DISTINCT FROM EXCLUDED.embedding_content_sha256
    OR existing.embedding IS DISTINCT FROM EXCLUDED.embedding
"""


def _ensure_unique_chunk_keys(chunks: Sequence[KnowledgeChunk]) -> None:
    keys = [(chunk.corpus_version, chunk.chunk_id) for chunk in chunks]
    if len(keys) != len(set(keys)):
        raise ValueError("chunks must have unique corpus_version and chunk_id pairs")


def _ensure_unique_embedding_keys(embeddings: Sequence[EmbeddingRecord]) -> None:
    keys = [
        (embedding.corpus_version, embedding.chunk_id, embedding.embedding_model)
        for embedding in embeddings
    ]
    if len(keys) != len(set(keys)):
        raise ValueError("embeddings must have unique corpus, chunk, and model keys")
