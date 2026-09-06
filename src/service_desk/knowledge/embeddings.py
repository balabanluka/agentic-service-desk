"""Small OpenAI embeddings boundary for future knowledge ingestion."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Protocol

from openai import OpenAI


logger = logging.getLogger(__name__)


class EmbeddingClientError(RuntimeError):
    """Raised when an embedding provider cannot return a safe embedding batch."""


class EmbeddingClient(Protocol):
    """Dependency-injected embedding boundary used by knowledge ingestion."""

    def embed(
        self, inputs: Sequence[str], *, model: str, dimensions: int
    ) -> tuple[tuple[float, ...], ...]:
        """Return one vector per input, in the same input order."""


class OpenAIEmbeddingClient:
    """OpenAI embeddings API implementation with no retrieval responsibilities."""

    def __init__(self, api_key: str) -> None:
        self._client = OpenAI(api_key=api_key)

    def embed(
        self, inputs: Sequence[str], *, model: str, dimensions: int
    ) -> tuple[tuple[float, ...], ...]:
        if not inputs:
            return ()
        try:
            response = self._client.embeddings.create(
                model=model,
                input=list(inputs),
                dimensions=dimensions,
                encoding_format="float",
            )
        except Exception as exc:  # SDK/network failures are an external boundary.
            logger.exception(
                "OpenAI embeddings request failed [model=%s, dimensions=%s, input_count=%s, "
                "error_type=%s, error=%s]",
                model,
                dimensions,
                len(inputs),
                type(exc).__name__,
                exc,
            )
            raise EmbeddingClientError("OpenAI embeddings request failed") from exc

        ordered = sorted(response.data, key=lambda item: item.index)
        if [item.index for item in ordered] != list(range(len(inputs))):
            raise EmbeddingClientError("embedding provider returned an incomplete or unordered batch")
        return tuple(tuple(float(value) for value in item.embedding) for item in ordered)
