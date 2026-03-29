"""Serper API wrapper for web search.

Provides async search via Serper (Google Search API).
Used by agents that need broad web context.
"""

import logging
from typing import Any

import httpx

from core.config import SERPER_API_KEY

logger = logging.getLogger(__name__)

SERPER_SEARCH_URL = "https://google.serper.dev/search"


class SearchClient:
    """Async wrapper around the Serper search API."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or SERPER_API_KEY

    async def search(
        self,
        query: str,
        *,
        num_results: int = 10,
        search_type: str = "search",
    ) -> list[dict[str, Any]]:
        """
        Run a web search and return organic results.

        Args:
            query: Search query string.
            num_results: Number of results to return (max 100).
            search_type: 'search', 'news', 'images', 'places'.

        Returns:
            List of result dicts with title, link, snippet.
        """
        if not self._api_key:
            raise RuntimeError("SERPER_API_KEY must be set to use SearchClient")

        headers = {
            "X-API-KEY": self._api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "q": query,
            "num": num_results,
        }

        logger.info("Serper search: q=%r type=%s", query, search_type)
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = SERPER_SEARCH_URL
            if search_type == "news":
                url = "https://google.serper.dev/news"
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        results = data.get("organic", [])
        logger.info("Serper returned %d results", len(results))
        return results

    async def search_news(
        self, query: str, *, num_results: int = 10
    ) -> list[dict[str, Any]]:
        """Convenience: search news specifically."""
        return await self.search(query, num_results=num_results, search_type="news")

    async def health_check(self) -> bool:
        """Verify we can reach Serper."""
        try:
            await self.search("test", num_results=1)
            return True
        except Exception as exc:
            logger.warning("Serper health check failed: %s", exc)
            return False
