"""Research agent API routes — paper upload, management, and RAG queries."""

import logging
import shutil
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from core.embeddings import EmbeddingsClient
from core.pdf_parser import PDFParser
from core.research_db import ResearchDB

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/research", tags=["research"])

# Storage directory for uploaded papers
PAPERS_DIR = Path("/app/papers") if Path("/app").exists() else Path("./papers")
PAPERS_DIR.mkdir(parents=True, exist_ok=True)

# Initialize clients
embeddings_client = EmbeddingsClient()
pdf_parser = PDFParser(chunk_size=1000, chunk_overlap=200)
research_db = ResearchDB()


class PaperUploadResponse(BaseModel):
    """Response after uploading a paper."""
    paper_id: str
    title: str
    authors: List[str]
    year: Optional[int]
    page_count: int
    chunks_created: int
    duplicate_warning: Optional[str] = None


class PaperMetadata(BaseModel):
    """Paper metadata for listing."""
    id: str
    title: str
    authors: List[str]
    year: Optional[int]
    doi: Optional[str]
    page_count: int
    uploaded_at: str
    visible_on_dashboard: bool


class ChatRequest(BaseModel):
    """Request body for research chat."""
    message: str = Field(..., description="User's research question")
    session_id: Optional[str] = Field(None, description="Session ID for conversation continuity")


class ChatResponse(BaseModel):
    """Response from research agent."""
    response: str
    session_id: str
    sources_used: List[str] = Field(default_factory=list)


@router.post("/upload", response_model=PaperUploadResponse)
async def upload_paper(file: UploadFile = File(...)):
    """Upload a research paper (PDF) and process it for RAG.
    
    Steps:
    1. Save PDF to disk
    2. Extract metadata (title, authors, year, DOI)
    3. Check for duplicates (content hash + title similarity)
    4. Extract and chunk text
    5. Generate embeddings for each chunk
    6. Store in Supabase
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    try:
        # Save uploaded file temporarily
        temp_path = PAPERS_DIR / f"temp_{file.filename}"
        with temp_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        
        logger.info(f"Processing uploaded paper: {file.filename}")
        
        # Extract metadata
        metadata = pdf_parser.extract_metadata(temp_path)
        logger.info(f"Extracted metadata: {metadata['title']}")
        
        # Compute content hash for duplicate detection
        content_hash = pdf_parser.compute_content_hash(temp_path)
        
        # Check for exact duplicate by content hash
        if await research_db.check_content_hash_exists(content_hash):
            temp_path.unlink()
            raise HTTPException(
                status_code=409,
                detail="This paper has already been uploaded (exact duplicate detected)"
            )
        
        # Check for similar titles
        duplicate_warning = None
        similar_papers = await research_db.find_duplicate_papers(
            metadata["title"],
            threshold=0.85,
        )
        if similar_papers:
            similar_titles = [p["title"] for p in similar_papers[:2]]
            duplicate_warning = f"Similar papers found: {', '.join(similar_titles)}"
            logger.warning(duplicate_warning)
        
        # Save paper permanently
        paper_id_str = None
        final_path = PAPERS_DIR / f"{content_hash}.pdf"
        temp_path.rename(final_path)
        
        # Create paper record in DB
        paper = await research_db.create_paper(
            title=metadata["title"],
            file_path=str(final_path),
            content_hash=content_hash,
            authors=metadata["authors"],
            year=metadata["year"],
            doi=metadata["doi"],
            page_count=metadata["page_count"],
        )
        paper_id = UUID(paper["id"])
        paper_id_str = str(paper_id)
        
        logger.info(f"Created paper record: {paper_id}")
        
        # Extract and chunk text
        chunks = pdf_parser.extract_text_chunks(final_path)
        logger.info(f"Extracted {len(chunks)} chunks")
        
        # Generate embeddings in batches to avoid overwhelming the service
        batch_size = 10
        total_chunks = len(chunks)
        
        for i in range(0, total_chunks, batch_size):
            batch_chunks = chunks[i:i+batch_size]
            batch_texts = [chunk["content"] for chunk in batch_chunks]
            
            logger.info(f"Processing batch {i//batch_size + 1}/{(total_chunks + batch_size - 1)//batch_size}")
            
            try:
                embeddings = await embeddings_client.embed_texts(batch_texts)
            except Exception as e:
                logger.error(f"Failed to generate embeddings for batch {i//batch_size + 1}: {e}")
                # Clean up - delete the paper record
                await research_db.delete_paper(paper_id)
                if final_path.exists():
                    final_path.unlink()
                raise HTTPException(
                    status_code=500,
                    detail=f"Embedding generation failed at chunk {i}: {e}"
                )
            
            # Store chunks with embeddings
            for chunk, embedding in zip(batch_chunks, embeddings):
                await research_db.create_paper_chunk(
                    paper_id=paper_id,
                    chunk_index=chunk["chunk_index"],
                    content=chunk["content"],
                    embedding=embedding,
                    page_number=chunk["page_number"],
                )
        
        logger.info(f"Paper processed successfully: {paper_id} ({total_chunks} chunks)")
        
        return PaperUploadResponse(
            paper_id=paper_id_str,
            title=metadata["title"],
            authors=metadata["authors"],
            year=metadata["year"],
            page_count=metadata["page_count"],
            chunks_created=len(chunks),
            duplicate_warning=duplicate_warning,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Paper upload failed: {e}", exc_info=True)
        if temp_path.exists():
            temp_path.unlink()
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")


@router.get("/papers", response_model=List[PaperMetadata])
async def list_papers(visible_only: bool = True, limit: int = 100):
    """List all uploaded papers."""
    try:
        papers = await research_db.list_papers(visible_only=visible_only, limit=limit)
        return [
            PaperMetadata(
                id=p["id"],
                title=p["title"],
                authors=p["authors"],
                year=p["year"],
                doi=p["doi"],
                page_count=p["page_count"],
                uploaded_at=p["uploaded_at"],
                visible_on_dashboard=p["visible_on_dashboard"],
            )
            for p in papers
        ]
    except Exception as e:
        logger.error(f"Failed to list papers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list papers: {e}")


@router.delete("/papers/{paper_id}")
async def delete_paper(paper_id: str):
    """Delete a paper and all its chunks."""
    try:
        paper_uuid = UUID(paper_id)
        
        # Get paper to delete file
        paper = await research_db.get_paper(paper_uuid)
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")
        
        # Delete file
        file_path = Path(paper["file_path"])
        if file_path.exists():
            file_path.unlink()
        
        # Delete from DB (cascades to chunks)
        await research_db.delete_paper(paper_uuid)
        
        return {"status": "deleted", "paper_id": paper_id}
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid paper ID")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete paper: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")


@router.patch("/papers/{paper_id}/visibility")
async def toggle_paper_visibility(paper_id: str, visible: bool):
    """Toggle paper visibility on dashboard."""
    try:
        paper_uuid = UUID(paper_id)
        updated = await research_db.update_paper_visibility(paper_uuid, visible)
        return {"status": "updated", "visible": updated["visible_on_dashboard"]}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid paper ID")
    except Exception as e:
        logger.error(f"Failed to update visibility: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Update failed: {e}")


@router.post("/chat", response_model=ChatResponse)
async def research_chat(request: ChatRequest):
    """Chat with the research agent.
    
    The agent has access to:
    - search_papers: Semantic search over uploaded papers
    - search_research_notes: Search Obsidian research notes
    - analyze_with_sonnet: Advanced analysis using Claude Sonnet
    - cite_sources: Format citations
    """
    from main import research_agent
    
    try:
        response = await research_agent.chat(request.message)
        
        # TODO: Extract sources from agent response
        sources = []
        
        return ChatResponse(
            response=response,
            session_id=request.session_id or "default",
            sources_used=sources,
        )
    except Exception as e:
        logger.error(f"Research chat failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat failed: {e}")


@router.post("/reset")
async def reset_session():
    """Reset the research agent's conversation memory."""
    from main import research_agent
    
    try:
        research_agent.reset()
        return {"status": "reset"}
    except Exception as e:
        logger.error(f"Reset failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Reset failed: {e}")
