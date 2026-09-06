"""Explicit local CLI for exact pgvector knowledge retrieval."""

from __future__ import annotations

import argparse
import json

from service_desk.config import Settings
from service_desk.knowledge.embeddings import OpenAIEmbeddingClient
from service_desk.knowledge.repository import KnowledgeRepository
from service_desk.knowledge.retrieval import KnowledgeRetrievalError, KnowledgeRetriever


def main() -> None:
    parser = argparse.ArgumentParser(description="Search the synthetic knowledge corpus.")
    parser.add_argument("query", help="Natural-language knowledge query")
    parser.add_argument("--domain", default=None, help="Optional billing, support, or technical filter")
    parser.add_argument("--top-k", type=int, default=None, help="Number of results, from 1 to 10")
    arguments = parser.parse_args()

    settings = Settings()
    if settings.openai_api_key is None:
        raise SystemExit("OPENAI_API_KEY must be configured before knowledge retrieval")
    if settings.database_url is None:
        raise SystemExit("DATABASE_URL must be configured before knowledge retrieval")

    repository = KnowledgeRepository.connect(settings.database_url.get_secret_value())
    try:
        retriever = KnowledgeRetriever(
            repository=repository,
            embedding_client=OpenAIEmbeddingClient(settings.openai_api_key.get_secret_value()),
            embedding_model=settings.openai_embedding_model,
            embedding_dimensions=settings.openai_embedding_dimensions,
            corpus_version=settings.knowledge_corpus_version,
            default_top_k=settings.knowledge_default_top_k,
        )
        results = retriever.search(arguments.query, domain=arguments.domain, top_k=arguments.top_k)
    except KnowledgeRetrievalError as error:
        raise SystemExit(str(error)) from error
    finally:
        repository.close()

    print(
        json.dumps(
            {
                "corpus_version": settings.knowledge_corpus_version,
                "embedding_model": settings.openai_embedding_model,
                "domain": arguments.domain,
                "top_k": arguments.top_k or settings.knowledge_default_top_k,
                "results": [result.as_dict() for result in results],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
