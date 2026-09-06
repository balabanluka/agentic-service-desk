"""Idempotent embedding and persistence of deterministic knowledge chunks."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from service_desk.knowledge.chunking import KnowledgeBaseChunker, KnowledgeChunk
from service_desk.knowledge.embeddings import EmbeddingClient
from service_desk.knowledge.repository import (
    VECTOR_DIMENSIONS,
    EmbeddingRecord,
    ExistingChunk,
    ExistingEmbedding,
    KnowledgeRepository,
)


DEFAULT_EMBEDDING_BATCH_SIZE = 64


class KnowledgeIngestionError(RuntimeError):
    """Raised when a chunk corpus or embedding batch is unsafe to persist."""


@dataclass(frozen=True, slots=True)
class IngestionReport:
    corpus_version: str
    embedding_model: str
    chunks_seen: int
    embedded: int
    unchanged: int
    updated: int
    retired: int
    embedding_api_calls: int

    def as_dict(self) -> dict[str, object]:
        """Return CLI-safe metadata without raw chunk content or vectors."""

        return asdict(self)


class KnowledgeIngestor:
    """Embed only stale chunks, then atomically persist the complete corpus state."""

    def __init__(
        self,
        *,
        chunker: KnowledgeBaseChunker,
        repository: KnowledgeRepository,
        embedding_client: EmbeddingClient,
        embedding_model: str,
        embedding_dimensions: int,
        corpus_version: str,
        batch_size: int = DEFAULT_EMBEDDING_BATCH_SIZE,
    ) -> None:
        if not embedding_model:
            raise ValueError("embedding_model must not be empty")
        if embedding_dimensions != VECTOR_DIMENSIONS:
            raise ValueError(
                f"embedding_dimensions must match the pgvector schema ({VECTOR_DIMENSIONS})"
            )
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self._chunker = chunker
        self._repository = repository
        self._embedding_client = embedding_client
        self._embedding_model = embedding_model
        self._embedding_dimensions = embedding_dimensions
        self._corpus_version = corpus_version
        self._batch_size = batch_size

    def ingest_directory(
        self, knowledge_directory: Path, *, repository_root: Path | None = None
    ) -> IngestionReport:
        """Chunk a repository-relative Markdown corpus, then ingest it idempotently."""

        chunks = self._chunker.chunk_directory(
            knowledge_directory, repository_root=repository_root
        )
        return self.ingest_chunks(chunks)

    def ingest_chunks(self, chunks: Sequence[KnowledgeChunk]) -> IngestionReport:
        """Persist a validated corpus after all required embeddings are available."""

        current_chunks = tuple(chunks)
        self._validate_chunks(current_chunks)

        existing_chunks = self._repository.existing_chunks(self._corpus_version)
        existing_embeddings = self._repository.existing_embedding_fingerprints(
            self._corpus_version, self._embedding_model
        )
        chunks_to_embed = tuple(
            chunk
            for chunk in current_chunks
            if _requires_embedding(chunk, existing_embeddings.get(chunk.chunk_id))
        )
        embedding_records, api_calls = self._create_embedding_records(chunks_to_embed)
        updated = sum(
            _requires_chunk_update(chunk, existing_chunks.get(chunk.chunk_id))
            for chunk in current_chunks
        )

        # No persistence happens until every required provider response has passed validation.
        with self._repository.transaction():
            self._repository.upsert_chunks(current_chunks)
            self._repository.upsert_embeddings(embedding_records)
            retired = self._repository.retire_missing_chunks(
                self._corpus_version, tuple(chunk.chunk_id for chunk in current_chunks)
            )

        return IngestionReport(
            corpus_version=self._corpus_version,
            embedding_model=self._embedding_model,
            chunks_seen=len(current_chunks),
            embedded=len(embedding_records),
            unchanged=len(current_chunks) - len(chunks_to_embed),
            updated=updated,
            retired=retired,
            embedding_api_calls=api_calls,
        )

    def _validate_chunks(self, chunks: Sequence[KnowledgeChunk]) -> None:
        if not chunks:
            raise KnowledgeIngestionError("refusing to ingest an empty knowledge corpus")
        keys = [(chunk.corpus_version, chunk.chunk_id) for chunk in chunks]
        if len(keys) != len(set(keys)):
            raise KnowledgeIngestionError("knowledge chunks must have unique corpus and chunk IDs")
        unexpected_versions = {chunk.corpus_version for chunk in chunks} - {self._corpus_version}
        if unexpected_versions:
            raise KnowledgeIngestionError(
                f"chunk corpus_version does not match ingestion configuration: {sorted(unexpected_versions)}"
            )

    def _create_embedding_records(
        self, chunks: Sequence[KnowledgeChunk]
    ) -> tuple[tuple[EmbeddingRecord, ...], int]:
        records: list[EmbeddingRecord] = []
        api_calls = 0
        for batch in _batches(chunks, self._batch_size):
            vectors = self._embedding_client.embed(
                [chunk.content for chunk in batch],
                model=self._embedding_model,
                dimensions=self._embedding_dimensions,
            )
            api_calls += 1
            if len(vectors) != len(batch):
                raise KnowledgeIngestionError("embedding provider returned a different number of vectors")
            for chunk, vector in zip(batch, vectors, strict=True):
                if len(vector) != self._embedding_dimensions:
                    raise KnowledgeIngestionError(
                        f"embedding dimension for {chunk.chunk_id} does not match "
                        f"{self._embedding_dimensions}"
                    )
                records.append(
                    EmbeddingRecord(
                        corpus_version=chunk.corpus_version,
                        chunk_id=chunk.chunk_id,
                        embedding_model=self._embedding_model,
                        embedding_dimensions=self._embedding_dimensions,
                        embedding_content_sha256=chunk.content_sha256,
                        embedding=vector,
                    )
                )
        return tuple(records), api_calls


def _requires_embedding(chunk: KnowledgeChunk, existing: ExistingEmbedding | None) -> bool:
    return (
        existing is None
        or existing.embedding_content_sha256 != chunk.content_sha256
        or existing.embedding_dimensions != VECTOR_DIMENSIONS
    )


def _requires_chunk_update(chunk: KnowledgeChunk, existing: ExistingChunk | None) -> bool:
    return existing is None or existing.content_sha256 != chunk.content_sha256 or not existing.is_active


def _batches(items: Sequence[KnowledgeChunk], size: int) -> Iterable[Sequence[KnowledgeChunk]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]
