"""Embedding client — provider TBD.

Placeholder interface for when an embedding provider is chosen
(e.g. Voyage AI, which pairs well with Claude).
Not wired into the platform yet — will be needed for RAG pipeline.
"""

import logging

logger = logging.getLogger(__name__)


class EmbeddingsClient:
    """Async embedding interface — implement when RAG pipeline is built."""

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError("Embedding provider not configured yet")

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError("Embedding provider not configured yet")
