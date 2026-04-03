"""Reading assistant API routes — EPUB upload, chapters, TTS, progress, summaries."""

import logging
import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from agents.reading.tools import (
    _books_dir,
    _load_metadata,
    _load_progress,
    _save_progress,
    ingest_epub_file,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reading", tags=["reading"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None


class ProgressUpdate(BaseModel):
    chapter_index: int
    position: int = 0


# ---------------------------------------------------------------------------
# Book Management
# ---------------------------------------------------------------------------

@router.post("/upload")
async def upload_book(file: UploadFile = File(...)):
    """Upload an EPUB file for reading."""
    if not file.filename or not file.filename.lower().endswith(".epub"):
        raise HTTPException(status_code=400, detail="Only EPUB files are supported.")

    content = await file.read()
    if len(content) > 100 * 1024 * 1024:  # 100MB limit
        raise HTTPException(status_code=400, detail="File too large (max 100MB).")

    # Write to temp file for ebooklib
    with NamedTemporaryFile(suffix=".epub", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        metadata = ingest_epub_file(tmp_path)
    except Exception as e:
        logger.error("EPUB ingestion failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to process EPUB: {e}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return metadata


@router.get("/books")
async def list_books():
    """List all ingested books with progress."""
    books_dir = _books_dir()
    results = []
    for meta_file in sorted(books_dir.glob("*/metadata.json")):
        import json
        meta = json.loads(meta_file.read_text())
        progress = _load_progress(meta["book_id"])
        completed = len(progress.get("completed_chapters", []))
        results.append({
            **meta,
            "progress": {
                "chapter_index": progress["chapter_index"],
                "position": progress.get("position", 0),
                "completed_chapters": completed,
                "percent": int(completed / meta["chapter_count"] * 100) if meta["chapter_count"] > 0 else 0,
            },
        })
    return {"books": results}


@router.get("/books/{book_id}")
async def get_book(book_id: str):
    """Get metadata and progress for a specific book."""
    meta = _load_metadata(book_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Book not found: {book_id}")
    progress = _load_progress(book_id)
    return {**meta, "progress": progress}


@router.delete("/books/{book_id}")
async def delete_book(book_id: str):
    """Delete a book and all its data (chapters, summaries, progress)."""
    from agents.reading.tools import _book_dir
    book_path = _book_dir(book_id)
    if not book_path.exists():
        raise HTTPException(status_code=404, detail=f"Book not found: {book_id}")
    shutil.rmtree(book_path)
    return {"deleted": book_id}


@router.get("/books/{book_id}/chapters")
async def get_chapters(book_id: str):
    """List all chapters for a book."""
    meta = _load_metadata(book_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Book not found: {book_id}")
    progress = _load_progress(book_id)
    return {
        "book_id": book_id,
        "title": meta["title"],
        "current_chapter": progress["chapter_index"],
        "chapters": meta["chapters"],
    }


@router.get("/books/{book_id}/chapters/{chapter_index}")
async def get_chapter_text(book_id: str, chapter_index: int):
    """Get full text of a specific chapter."""
    from agents.reading.tools import _book_dir
    chapter_file = _book_dir(book_id) / "chapters" / f"{chapter_index:03d}.txt"
    if not chapter_file.exists():
        raise HTTPException(status_code=404, detail=f"Chapter {chapter_index} not found")
    return {"book_id": book_id, "chapter_index": chapter_index, "text": chapter_file.read_text()}


# ---------------------------------------------------------------------------
# Reading & Progress
# ---------------------------------------------------------------------------

@router.get("/books/{book_id}/read")
async def get_current_section(book_id: str, max_chars: int = 3000):
    """Get the current reading section based on progress.

    Returns text from current position, suitable for TTS (~2-3 min).
    """
    from agents.reading.tools import _book_dir
    meta = _load_metadata(book_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Book not found: {book_id}")

    progress = _load_progress(book_id)
    ch_idx = progress["chapter_index"]

    if ch_idx >= meta["chapter_count"]:
        return {"done": True, "message": "Book complete!"}

    chapter_file = _book_dir(book_id) / "chapters" / f"{ch_idx:03d}.txt"
    if not chapter_file.exists():
        raise HTTPException(status_code=404, detail="Chapter file missing")

    text = chapter_file.read_text()
    position = progress.get("position", 0)
    section = text[position:position + max_chars]

    # End at sentence boundary
    if position + max_chars < len(text):
        last_period = section.rfind(". ")
        if last_period > max_chars * 0.5:
            section = section[:last_period + 1]

    actual_chars = len(section)
    ch_title = meta["chapters"][ch_idx]["title"] if ch_idx < len(meta["chapters"]) else ""
    ch_pct = int((position + actual_chars) / len(text) * 100) if len(text) > 0 else 100

    return {
        "book_id": book_id,
        "chapter_index": ch_idx,
        "chapter_title": ch_title,
        "position": position,
        "chars_in_section": actual_chars,
        "chapter_percent": ch_pct,
        "text": section,
        "done": False,
    }


@router.post("/books/{book_id}/advance")
async def advance_position(book_id: str, chars_read: int):
    """Advance reading position after TTS playback."""
    meta = _load_metadata(book_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Book not found: {book_id}")

    progress = _load_progress(book_id)
    ch_idx = progress["chapter_index"]

    from agents.reading.tools import _book_dir
    chapter_file = _book_dir(book_id) / "chapters" / f"{ch_idx:03d}.txt"
    if not chapter_file.exists():
        return {"done": True, "message": "Already at end of book."}

    chapter_len = len(chapter_file.read_text())
    new_position = progress.get("position", 0) + chars_read

    if new_position >= chapter_len:
        completed = progress.get("completed_chapters", [])
        if ch_idx not in completed:
            completed.append(ch_idx)
        progress["completed_chapters"] = completed
        progress["chapter_index"] = ch_idx + 1
        progress["position"] = 0
        _save_progress(book_id, progress)

        if ch_idx + 1 >= meta["chapter_count"]:
            return {"done": True, "message": "Book complete!"}

        next_title = meta["chapters"][ch_idx + 1]["title"]
        return {"done": False, "chapter_complete": True, "next_chapter": next_title}
    else:
        progress["position"] = new_position
        _save_progress(book_id, progress)
        return {"done": False, "chapter_complete": False, "position": new_position}


@router.post("/books/{book_id}/progress")
async def update_progress(book_id: str, update: ProgressUpdate):
    """Jump to a specific chapter and position."""
    meta = _load_metadata(book_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Book not found: {book_id}")
    if update.chapter_index < 0 or update.chapter_index >= meta["chapter_count"]:
        raise HTTPException(status_code=400, detail="Invalid chapter index")

    progress = _load_progress(book_id)
    progress["chapter_index"] = update.chapter_index
    progress["position"] = update.position
    _save_progress(book_id, progress)
    return {"status": "ok", "chapter_index": update.chapter_index, "position": update.position}


# ---------------------------------------------------------------------------
# Chat (agent-based Q&A about books)
# ---------------------------------------------------------------------------

@router.post("/chat")
async def reading_chat(request: ChatRequest):
    """Chat with the reading agent about your books."""
    from main import reading_agent
    try:
        reply = await reading_agent.chat(request.message, thread_id=request.thread_id)
        return {"reply": reply}
    except Exception as e:
        logger.error("Reading chat failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Summarize
# ---------------------------------------------------------------------------

@router.post("/books/{book_id}/chapters/{chapter_index}/summarize")
async def summarize_chapter(book_id: str, chapter_index: int):
    """Generate a summary of a specific chapter using the LLM."""
    from agents.reading.tools import _book_dir
    from main import reading_agent

    chapter_file = _book_dir(book_id) / "chapters" / f"{chapter_index:03d}.txt"
    if not chapter_file.exists():
        raise HTTPException(status_code=404, detail=f"Chapter {chapter_index} not found")

    meta = _load_metadata(book_id)
    ch_title = meta["chapters"][chapter_index]["title"] if chapter_index < len(meta["chapters"]) else ""

    # Check for cached summary
    summary_file = _book_dir(book_id) / "summaries" / f"{chapter_index:03d}.md"
    if summary_file.exists():
        return {"book_id": book_id, "chapter_index": chapter_index, "summary": summary_file.read_text(), "cached": True}

    text = chapter_file.read_text()
    prompt = (
        f"Summarize this chapter from '{meta['title']}' (Chapter: {ch_title}).\n\n"
        f"Produce:\n"
        f"1. **TL;DR** — 1-2 sentence overview\n"
        f"2. **Key Points** — 3-5 bullet points\n"
        f"3. **Key Terms** — Important terminology with brief definitions\n"
        f"4. **Practical Takeaways** — What should the reader do or remember\n\n"
        f"Chapter text:\n{text[:15000]}"  # Limit to ~15k chars for Haiku context
    )

    try:
        reply = await reading_agent.chat(prompt)
        # Cache the summary
        summary_file.parent.mkdir(parents=True, exist_ok=True)
        summary_file.write_text(reply)
        return {"book_id": book_id, "chapter_index": chapter_index, "summary": reply, "cached": False}
    except Exception as e:
        logger.error("Summarization failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Web UI — Teleprompter / Reader
# ---------------------------------------------------------------------------

@router.get("/ui", response_class=HTMLResponse)
async def reading_ui():
    """Serve the touch-optimized reading assistant web UI."""
    static_dir = Path(__file__).resolve().parent.parent.parent / "static"
    html_path = static_dir / "reader.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="reader.html not found")
    return HTMLResponse(html_path.read_text())


@router.get("/manage", response_class=HTMLResponse)
async def reading_manage():
    """Serve the desktop book management UI (upload, delete, view library)."""
    static_dir = Path(__file__).resolve().parent.parent.parent / "static"
    html_path = static_dir / "manage.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="manage.html not found")
    return HTMLResponse(html_path.read_text())
