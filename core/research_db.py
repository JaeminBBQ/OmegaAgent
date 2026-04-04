"""Supabase client for research papers RAG system."""

import logging
from typing import List, Dict, Any, Optional
from uuid import UUID

from supabase import create_client, Client

from core.config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)


class ResearchDB:
    """Database client for research papers and notes."""

    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set")
        self.client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # --- Papers ---

    async def create_paper(
        self,
        title: str,
        file_path: str,
        content_hash: str,
        authors: Optional[List[str]] = None,
        year: Optional[int] = None,
        doi: Optional[str] = None,
        page_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create a new paper record."""
        data = {
            "title": title,
            "file_path": file_path,
            "content_hash": content_hash,
            "authors": authors or [],
            "year": year,
            "doi": doi,
            "page_count": page_count,
        }
        result = self.client.table("papers").insert(data).execute()
        return result.data[0]

    async def get_paper(self, paper_id: UUID) -> Optional[Dict[str, Any]]:
        """Get paper by ID."""
        result = self.client.table("papers").select("*").eq("id", str(paper_id)).execute()
        return result.data[0] if result.data else None

    async def list_papers(
        self,
        visible_only: bool = True,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List all papers."""
        query = self.client.table("papers").select("*")
        if visible_only:
            query = query.eq("visible_on_dashboard", True)
        result = query.order("uploaded_at", desc=True).limit(limit).execute()
        return result.data

    async def update_paper_visibility(
        self,
        paper_id: UUID,
        visible: bool,
    ) -> Dict[str, Any]:
        """Toggle paper visibility on dashboard."""
        result = (
            self.client.table("papers")
            .update({"visible_on_dashboard": visible})
            .eq("id", str(paper_id))
            .execute()
        )
        return result.data[0]

    async def delete_paper(self, paper_id: UUID) -> None:
        """Delete paper and all its chunks (cascades)."""
        self.client.table("papers").delete().eq("id", str(paper_id)).execute()

    async def find_duplicate_papers(
        self,
        title: str,
        threshold: float = 0.9,
    ) -> List[Dict[str, Any]]:
        """Find papers with similar titles using trigram similarity."""
        result = self.client.rpc(
            "find_duplicate_papers",
            {"paper_title": title, "similarity_threshold": threshold},
        ).execute()
        return result.data

    async def check_content_hash_exists(self, content_hash: str) -> bool:
        """Check if a paper with this content hash already exists."""
        result = (
            self.client.table("papers")
            .select("id")
            .eq("content_hash", content_hash)
            .execute()
        )
        return len(result.data) > 0

    # --- Paper Chunks ---

    async def create_paper_chunk(
        self,
        paper_id: UUID,
        chunk_index: int,
        content: str,
        embedding: List[float],
        page_number: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create a paper chunk with embedding."""
        data = {
            "paper_id": str(paper_id),
            "chunk_index": chunk_index,
            "content": content,
            "embedding": embedding,
            "page_number": page_number,
        }
        result = self.client.table("paper_chunks").insert(data).execute()
        return result.data[0]

    async def search_paper_chunks(
        self,
        query_embedding: List[float],
        threshold: float = 0.7,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Semantic search over paper chunks."""
        result = self.client.rpc(
            "search_paper_chunks",
            {
                "query_embedding": query_embedding,
                "match_threshold": threshold,
                "match_count": limit,
            },
        ).execute()
        return result.data

    # --- Research Notes ---

    async def upsert_research_note(
        self,
        file_path: str,
        title: str,
        content: str,
        embedding: List[float],
    ) -> Dict[str, Any]:
        """Create or update a research note with embedding."""
        data = {
            "file_path": file_path,
            "title": title,
            "content": content,
            "embedding": embedding,
        }
        result = (
            self.client.table("research_notes")
            .upsert(data, on_conflict="file_path")
            .execute()
        )
        return result.data[0]

    async def search_research_notes(
        self,
        query_embedding: List[float],
        threshold: float = 0.7,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Semantic search over research notes."""
        result = self.client.rpc(
            "search_research_notes",
            {
                "query_embedding": query_embedding,
                "match_threshold": threshold,
                "match_count": limit,
            },
        ).execute()
        return result.data

    async def delete_research_note(self, file_path: str) -> None:
        """Delete a research note."""
        self.client.table("research_notes").delete().eq("file_path", file_path).execute()
