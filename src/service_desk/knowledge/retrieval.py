"""Exact, model-scoped pgvector retrieval for the frozen knowledge corpus."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from service_desk.knowledge.embeddings import EmbeddingClient
from service_desk.knowledge.repository import (
    VECTOR_DIMENSIONS,
    KnowledgeRepository,
    RetrievedKnowledgeChunk,
)


KNOWLEDGE_DOMAINS = frozenset({"billing", "support", "technical"})
MIN_TOP_K = 1
MAX_TOP_K = 10


class KnowledgeRetrievalError(ValueError):
    """Raised when a retrieval request is invalid or an embedding response is unsafe."""


class KnowledgeSearchProvider(Protocol):
    """Dependency-injected retrieval boundary used by controlled workflows."""

    def search(
        self, query: str, *, domain: str | None = None, top_k: int | None = None
    ) -> tuple["KnowledgeSearchResult", ...]:
        """Return domain-filtered knowledge results for one query."""


@dataclass(frozen=True, slots=True)
class KnowledgeSearchResult:
    """A ranked knowledge passage; similarity is a ranking signal, not confidence."""

    rank: int
    chunk_id: str
    chunking_version: str
    corpus_version: str
    document_id: str
    document_title: str
    domain: str
    product: str
    heading_path: tuple[str, ...]
    included_heading_paths: tuple[tuple[str, ...], ...]
    chunk_index: int
    source_path: str
    content: str
    word_count: int
    content_sha256: str
    source_commit: str
    cosine_distance: float
    cosine_similarity: float

    def as_dict(self) -> dict[str, object]:
        """Return JSON-safe result data without the query vector."""

        return {
            "rank": self.rank,
            "chunk_id": self.chunk_id,
            "chunking_version": self.chunking_version,
            "corpus_version": self.corpus_version,
            "document_id": self.document_id,
            "document_title": self.document_title,
            "domain": self.domain,
            "product": self.product,
            "heading_path": list(self.heading_path),
            "included_heading_paths": [list(path) for path in self.included_heading_paths],
            "chunk_index": self.chunk_index,
            "source_path": self.source_path,
            "content": self.content,
            "word_count": self.word_count,
            "content_sha256": self.content_sha256,
            "source_commit": self.source_commit,
            "cosine_distance": self.cosine_distance,
            "cosine_similarity": self.cosine_similarity,
        }


class KnowledgeRetriever:
    """Embed one query and retrieve exact cosine-ranked active knowledge chunks."""

    def __init__(
        self,
        *,
        repository: KnowledgeRepository,
        embedding_client: EmbeddingClient,
        embedding_model: str,
        embedding_dimensions: int,
        corpus_version: str,
        default_top_k: int = 4,
    ) -> None:
        if not embedding_model:
            raise ValueError("embedding_model must not be empty")
        if embedding_dimensions != VECTOR_DIMENSIONS:
            raise ValueError(
                f"embedding_dimensions must match the pgvector schema ({VECTOR_DIMENSIONS})"
            )
        _validate_top_k(default_top_k)
        self._repository = repository
        self._embedding_client = embedding_client
        self._embedding_model = embedding_model
        self._embedding_dimensions = embedding_dimensions
        self._corpus_version = corpus_version
        self._default_top_k = default_top_k

    def search(
        self, query: str, *, domain: str | None = None, top_k: int | None = None
    ) -> tuple[KnowledgeSearchResult, ...]:
        """Return exact cosine-ranked results for one non-empty knowledge query."""

        normalized_query = query.strip()
        if not normalized_query:
            raise KnowledgeRetrievalError("query must not be blank")
        if domain is not None and domain not in KNOWLEDGE_DOMAINS:
            raise KnowledgeRetrievalError(
                f"domain must be one of: {', '.join(sorted(KNOWLEDGE_DOMAINS))}"
            )
        resolved_top_k = self._default_top_k if top_k is None else top_k
        _validate_top_k(resolved_top_k)

        vectors = self._embedding_client.embed(
            (normalized_query,),
            model=self._embedding_model,
            dimensions=self._embedding_dimensions,
        )
        if len(vectors) != 1:
            raise KnowledgeRetrievalError("embedding provider must return exactly one query vector")
        query_vector = vectors[0]
        if len(query_vector) != self._embedding_dimensions:
            raise KnowledgeRetrievalError(
                f"query embedding dimension does not match {self._embedding_dimensions}"
            )

        matches = self._repository.search_active_chunks(
            corpus_version=self._corpus_version,
            embedding_model=self._embedding_model,
            query_embedding=query_vector,
            domain=domain,
            top_k=resolved_top_k,
        )
        return tuple(
            _search_result(match, rank=index)
            for index, match in enumerate(matches, start=1)
        )


class DatabaseKnowledgeRetriever:
    """Lazy production adapter that opens a database connection only for a search."""

    def __init__(
        self,
        *,
        database_url: str,
        embedding_client: EmbeddingClient,
        embedding_model: str,
        embedding_dimensions: int,
        corpus_version: str,
        default_top_k: int = 4,
    ) -> None:
        self._database_url = database_url
        self._embedding_client = embedding_client
        self._embedding_model = embedding_model
        self._embedding_dimensions = embedding_dimensions
        self._corpus_version = corpus_version
        self._default_top_k = default_top_k

    def search(
        self, query: str, *, domain: str | None = None, top_k: int | None = None
    ) -> tuple[KnowledgeSearchResult, ...]:
        repository = KnowledgeRepository.connect(self._database_url)
        try:
            return KnowledgeRetriever(
                repository=repository,
                embedding_client=self._embedding_client,
                embedding_model=self._embedding_model,
                embedding_dimensions=self._embedding_dimensions,
                corpus_version=self._corpus_version,
                default_top_k=self._default_top_k,
            ).search(query, domain=domain, top_k=top_k)
        finally:
            repository.close()


def _validate_top_k(top_k: int) -> None:
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not MIN_TOP_K <= top_k <= MAX_TOP_K:
        raise KnowledgeRetrievalError(f"top_k must be between {MIN_TOP_K} and {MAX_TOP_K}")


def _search_result(match: RetrievedKnowledgeChunk, *, rank: int) -> KnowledgeSearchResult:
    return KnowledgeSearchResult(
        rank=rank,
        chunk_id=match.chunk_id,
        chunking_version=match.chunking_version,
        corpus_version=match.corpus_version,
        document_id=match.document_id,
        document_title=match.document_title,
        domain=match.domain,
        product=match.product,
        heading_path=match.heading_path,
        included_heading_paths=match.included_heading_paths,
        chunk_index=match.chunk_index,
        source_path=match.source_path,
        content=match.content,
        word_count=match.word_count,
        content_sha256=match.content_sha256,
        source_commit=match.source_commit,
        cosine_distance=match.cosine_distance,
        cosine_similarity=1.0 - match.cosine_distance,
    )
