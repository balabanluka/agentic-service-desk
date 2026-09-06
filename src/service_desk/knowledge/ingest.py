"""Explicit local CLI for idempotent V2 knowledge ingestion."""

from __future__ import annotations

import json
from pathlib import Path

from service_desk.config import Settings
from service_desk.knowledge.chunking import KnowledgeBaseChunker
from service_desk.knowledge.embeddings import OpenAIEmbeddingClient
from service_desk.knowledge.ingestion import KnowledgeIngestor
from service_desk.knowledge.repository import KnowledgeRepository


def main() -> None:
    settings = Settings()
    if settings.openai_api_key is None:
        raise SystemExit("OPENAI_API_KEY must be configured before knowledge ingestion")
    if settings.database_url is None:
        raise SystemExit("DATABASE_URL must be configured before knowledge ingestion")

    repository_root = Path(__file__).resolve().parents[3]
    repository = KnowledgeRepository.connect(settings.database_url.get_secret_value())
    try:
        ingestor = KnowledgeIngestor(
            chunker=KnowledgeBaseChunker(corpus_version=settings.knowledge_corpus_version),
            repository=repository,
            embedding_client=OpenAIEmbeddingClient(settings.openai_api_key.get_secret_value()),
            embedding_model=settings.openai_embedding_model,
            embedding_dimensions=settings.openai_embedding_dimensions,
            corpus_version=settings.knowledge_corpus_version,
        )
        report = ingestor.ingest_directory(
            repository_root / "knowledge", repository_root=repository_root
        )
    finally:
        repository.close()
    print(json.dumps(report.as_dict(), sort_keys=True))


if __name__ == "__main__":
    main()
