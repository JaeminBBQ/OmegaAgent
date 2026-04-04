"""Embedding client for self-hosted sentence-transformers service.

Uses bge-large-en-v1.5 running on GPU server (172.16.0.94:8082).
1024-dimensional embeddings optimized for retrieval tasks.
"""

import logging
from typing import List

import httpx

logger = logging.getLogger(__name__)


class EmbeddingsClient:
    """Client for self-hosted embedding service."""

    def __init__(self, base_url: str = "http://172.16.0.94:8082"):
        self.base_url = base_url
        self._timeout = httpx.Timeout(30.0, connect=5.0)

    async def embed(self, text: str) -> List[float]:
        """Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            1024-dimensional embedding vector
        """
        result = await self.embed_batch([text])
        return result[0]

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed (max 100 per batch)
            
        Returns:
            List of 1024-dimensional embedding vectors
        """
        if not texts:
            return []
        
        if len(texts) > 100:
            logger.warning(f"Batch size {len(texts)} exceeds 100, splitting into chunks")
            # Process in chunks of 100
            results = []
            for i in range(0, len(texts), 100):
                chunk = texts[i:i+100]
                chunk_results = await self.embed_batch(chunk)
                results.extend(chunk_results)
            return results
        
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self.base_url}/v1/embeddings",
                    json={"texts": texts, "normalize": True},
                )
                response.raise_for_status()
                data = response.json()
                return data["embeddings"]
        except httpx.HTTPError as e:
            logger.error(f"Embedding request failed: {e}")
            raise RuntimeError(f"Failed to generate embeddings: {e}")

    async def health_check(self) -> dict:
        """Check if embedding service is healthy."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(f"{self.base_url}/v1/health")
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Embedding service health check failed: {e}")
            return {"status": "error", "error": str(e)}
