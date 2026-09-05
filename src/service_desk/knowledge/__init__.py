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

__all__ = [
    "CHUNKING_VERSION",
    "CORPUS_VERSION",
    "FROZEN_SOURCE_COMMIT",
    "KnowledgeBaseChunker",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "KnowledgeDocumentError",
]
