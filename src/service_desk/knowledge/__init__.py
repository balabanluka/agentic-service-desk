"""Deterministic parsing and chunking for the frozen knowledge base."""

from service_desk.knowledge.chunking import (
    CHUNKING_VERSION,
    CORPUS_VERSION,
    FROZEN_SOURCE_COMMIT,
    KnowledgeBaseChunker,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentError,
)
from service_desk.knowledge.repository import EmbeddingRecord, KnowledgeRepository

__all__ = [
    "CHUNKING_VERSION",
    "CORPUS_VERSION",
    "FROZEN_SOURCE_COMMIT",
    "KnowledgeBaseChunker",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "KnowledgeDocumentError",
    "EmbeddingRecord",
    "KnowledgeRepository",
]
