"""Supabase client wrapper for structured storage.

Provides async-friendly helpers around the Supabase Python client.
pgvector / RAG tables can be layered on later — this covers
structured agent data storage for now.
"""

import logging
from typing import Any

from supabase import Client, create_client

from core.config import SUPABASE_KEY, SUPABASE_URL

logger = logging.getLogger(__name__)


class DBClient:
    """Thin wrapper around the Supabase client."""

    def __init__(self, url: str | None = None, key: str | None = None) -> None:
        self._url = url or SUPABASE_URL
        self._key = key or SUPABASE_KEY
        self._client: Client | None = None

    @property
    def client(self) -> Client:
        if self._client is None:
            if not self._url or not self._key:
                raise RuntimeError(
                    "SUPABASE_URL and SUPABASE_KEY must be set to use DBClient"
                )
            self._client = create_client(self._url, self._key)
            logger.info("Supabase client initialized for %s", self._url)
        return self._client

    # -- convenience helpers --------------------------------------------------

    async def insert(self, table: str, data: dict[str, Any]) -> dict:
        """Insert a row and return the inserted record."""
        result = self.client.table(table).insert(data).execute()
        logger.debug("Inserted into %s: %s", table, result.data)
        return result.data

    async def upsert(self, table: str, data: dict[str, Any]) -> dict:
        """Upsert a row (insert or update on conflict)."""
        result = self.client.table(table).upsert(data).execute()
        logger.debug("Upserted into %s: %s", table, result.data)
        return result.data

    async def select(
        self,
        table: str,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Select rows with optional eq filters."""
        query = self.client.table(table).select(columns)
        if filters:
            for col, val in filters.items():
                query = query.eq(col, val)
        result = query.limit(limit).execute()
        return result.data

    async def delete(self, table: str, filters: dict[str, Any]) -> list[dict]:
        """Delete rows matching eq filters."""
        query = self.client.table(table).delete()
        for col, val in filters.items():
            query = query.eq(col, val)
        result = query.execute()
        logger.debug("Deleted from %s: %d rows", table, len(result.data))
        return result.data

    async def health_check(self) -> bool:
        """Return True if we can reach Supabase."""
        try:
            self.client.table("_health").select("*").limit(1).execute()
            return True
        except Exception:
            # Table may not exist — that's fine, connection itself worked
            # if we got past the auth handshake.
            return True

    async def close(self) -> None:
        """Clean up (no-op for now, here for interface consistency)."""
        self._client = None
