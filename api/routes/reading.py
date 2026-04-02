"""Reading assistant API routes — EPUB upload, chapters, TTS, progress, summaries."""

import logging
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
    """Serve the reading assistant web UI (teleprompter mode)."""
    return _READER_HTML


_READER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OmegaReader</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Georgia', serif; background: #0d1117; color: #c9d1d9; }

        /* Header */
        .header {
            background: #161b22; border-bottom: 1px solid #30363d;
            padding: 12px 20px; display: flex; align-items: center; gap: 16px;
            position: fixed; top: 0; left: 0; right: 0; z-index: 100;
        }
        .header h1 { font-size: 1.1em; color: #58a6ff; flex-shrink: 0; }
        .header select, .header button {
            background: #21262d; color: #c9d1d9; border: 1px solid #30363d;
            padding: 6px 12px; border-radius: 6px; font-size: 0.9em; cursor: pointer;
        }
        .header button:hover { background: #30363d; }
        .header .spacer { flex: 1; }
        .progress-text { font-size: 0.85em; color: #8b949e; }

        /* Main reading area */
        .reader {
            max-width: 720px; margin: 80px auto 120px; padding: 20px;
            font-size: 1.3em; line-height: 1.8;
        }
        .reader .chapter-title {
            color: #58a6ff; font-size: 1.4em; margin-bottom: 20px;
            border-bottom: 1px solid #30363d; padding-bottom: 10px;
        }
        .reader .text-content { white-space: pre-wrap; }
        .reader .text-content .word-highlight {
            background: #1f6feb33; border-radius: 3px; padding: 0 2px;
        }

        /* Controls */
        .controls {
            position: fixed; bottom: 0; left: 0; right: 0;
            background: #161b22; border-top: 1px solid #30363d;
            padding: 12px 20px; display: flex; align-items: center; gap: 12px;
            justify-content: center;
        }
        .controls button {
            background: #238636; color: white; border: none;
            padding: 10px 24px; border-radius: 8px; font-size: 1em;
            cursor: pointer; min-width: 100px;
        }
        .controls button:hover { background: #2ea043; }
        .controls button.secondary { background: #21262d; border: 1px solid #30363d; color: #c9d1d9; }
        .controls button.secondary:hover { background: #30363d; }
        .controls button:disabled { opacity: 0.5; cursor: not-allowed; }

        /* Book selector overlay */
        .overlay {
            position: fixed; inset: 0; background: #0d1117ee;
            display: flex; align-items: center; justify-content: center; z-index: 200;
        }
        .overlay.hidden { display: none; }
        .overlay .panel {
            background: #161b22; border: 1px solid #30363d; border-radius: 12px;
            padding: 30px; max-width: 600px; width: 90%;
        }
        .overlay h2 { color: #58a6ff; margin-bottom: 16px; }
        .book-card {
            background: #21262d; border: 1px solid #30363d; border-radius: 8px;
            padding: 16px; margin-bottom: 12px; cursor: pointer;
        }
        .book-card:hover { border-color: #58a6ff; }
        .book-card h3 { margin-bottom: 4px; }
        .book-card .meta { color: #8b949e; font-size: 0.9em; }

        /* Upload area */
        .upload-area {
            border: 2px dashed #30363d; border-radius: 8px; padding: 24px;
            text-align: center; margin-top: 16px; cursor: pointer;
        }
        .upload-area:hover { border-color: #58a6ff; }
        .upload-area input { display: none; }

        /* Summary panel */
        .summary-panel {
            max-width: 720px; margin: 80px auto 120px; padding: 20px;
            display: none;
        }
        .summary-panel.active { display: block; }
        .summary-panel h2 { color: #58a6ff; margin-bottom: 16px; }
        .summary-content { line-height: 1.6; }

        /* Loading */
        .loading { text-align: center; padding: 40px; color: #8b949e; }
    </style>
</head>
<body>
    <div class="header">
        <h1>📖 OmegaReader</h1>
        <span id="bookTitle" class="progress-text">No book selected</span>
        <div class="spacer"></div>
        <span id="progressText" class="progress-text"></span>
        <button onclick="showBookSelector()">📚 Books</button>
        <button onclick="showSummary()">📝 Summary</button>
    </div>

    <div class="reader" id="reader">
        <div class="loading" id="placeholder">Select a book to start reading</div>
        <div class="chapter-title" id="chapterTitle" style="display:none"></div>
        <div class="text-content" id="textContent"></div>
    </div>

    <div class="summary-panel" id="summaryPanel">
        <h2>Chapter Summary</h2>
        <div class="summary-content" id="summaryContent">
            <div class="loading">Click "Summarize" to generate</div>
        </div>
    </div>

    <div class="controls">
        <button class="secondary" onclick="prevSection()" id="btnPrev">⏮ Prev</button>
        <button onclick="togglePlay()" id="btnPlay">▶ Play</button>
        <button class="secondary" onclick="nextSection()" id="btnNext">Next ⏭</button>
        <button class="secondary" onclick="summarizeChapter()" id="btnSummarize">📝 Summarize</button>
    </div>

    <!-- Book selector overlay -->
    <div class="overlay" id="bookSelector">
        <div class="panel">
            <h2>📚 Your Books</h2>
            <div id="bookList"><div class="loading">Loading...</div></div>
            <div class="upload-area" onclick="document.getElementById('epubInput').click()">
                <input type="file" id="epubInput" accept=".epub" onchange="uploadBook(this.files[0])">
                <p>📤 Click to upload an EPUB</p>
                <p class="meta">or drag and drop</p>
            </div>
        </div>
    </div>

<script>
const API = window.location.origin;
let currentBook = null;
let currentSection = null;
let isPlaying = false;
let ttsAudio = null;

// --- Book Management ---
async function loadBooks() {
    const resp = await fetch(`${API}/reading/books`);
    const data = await resp.json();
    const list = document.getElementById('bookList');

    if (data.books.length === 0) {
        list.innerHTML = '<p class="meta">No books yet. Upload an EPUB to get started.</p>';
        return;
    }

    list.innerHTML = data.books.map(b => `
        <div class="book-card" onclick="selectBook('${b.book_id}')">
            <h3>${b.title}</h3>
            <div class="meta">${b.author} · ${b.chapter_count} chapters · ${b.total_words.toLocaleString()} words</div>
            <div class="meta">Progress: ${b.progress.percent}% · Chapter ${b.progress.chapter_index + 1}/${b.chapter_count}</div>
        </div>
    `).join('');
}

async function uploadBook(file) {
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    document.getElementById('bookList').innerHTML = '<div class="loading">Processing EPUB...</div>';

    try {
        const resp = await fetch(`${API}/reading/upload`, { method: 'POST', body: form });
        if (!resp.ok) throw new Error(await resp.text());
        await loadBooks();
    } catch (e) {
        alert('Upload failed: ' + e.message);
        await loadBooks();
    }
}

function showBookSelector() {
    document.getElementById('bookSelector').classList.remove('hidden');
    loadBooks();
}

async function selectBook(bookId) {
    currentBook = bookId;
    document.getElementById('bookSelector').classList.add('hidden');
    document.getElementById('summaryPanel').classList.remove('active');
    document.getElementById('reader').style.display = 'block';
    await loadSection();
}

// --- Reading ---
async function loadSection() {
    if (!currentBook) return;
    const resp = await fetch(`${API}/reading/books/${currentBook}/read`);
    const data = await resp.json();

    if (data.done) {
        document.getElementById('textContent').textContent = '🎉 Book complete! Well done.';
        document.getElementById('chapterTitle').style.display = 'none';
        return;
    }

    currentSection = data;
    document.getElementById('placeholder').style.display = 'none';
    document.getElementById('chapterTitle').style.display = 'block';
    document.getElementById('chapterTitle').textContent = data.chapter_title;
    document.getElementById('textContent').textContent = data.text;
    document.getElementById('bookTitle').textContent = data.chapter_title;
    document.getElementById('progressText').textContent = `Ch ${data.chapter_index + 1} · ${data.chapter_percent}%`;
}

async function nextSection() {
    if (!currentBook || !currentSection) return;
    // Advance position
    await fetch(`${API}/reading/books/${currentBook}/advance?chars_read=${currentSection.chars_in_section}`, { method: 'POST' });
    await loadSection();
}

async function prevSection() {
    if (!currentBook || !currentSection) return;
    // Go back by setting position backward
    const newPos = Math.max(0, currentSection.position - 3000);
    await fetch(`${API}/reading/books/${currentBook}/progress`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chapter_index: currentSection.chapter_index, position: newPos }),
    });
    await loadSection();
}

// --- TTS Playback ---
async function togglePlay() {
    if (isPlaying) {
        stopPlay();
        return;
    }
    if (!currentSection) return;

    isPlaying = true;
    document.getElementById('btnPlay').textContent = '⏸ Pause';
    await playCurrentSection();
}

function stopPlay() {
    isPlaying = false;
    document.getElementById('btnPlay').textContent = '▶ Play';
    if (ttsAudio) {
        ttsAudio.pause();
        ttsAudio = null;
    }
}

async function playCurrentSection() {
    if (!isPlaying || !currentSection) { stopPlay(); return; }

    const text = currentSection.text;
    if (!text.trim()) { stopPlay(); return; }

    try {
        // Request TTS
        const resp = await fetch(`${API}/speech/tts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text, voice: 'af_heart', provider: 'kokoro' }),
        });

        if (!resp.ok) { stopPlay(); return; }

        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        ttsAudio = new Audio(url);

        ttsAudio.onended = async () => {
            URL.revokeObjectURL(url);
            if (!isPlaying) return;
            // Advance and load next section
            await fetch(`${API}/reading/books/${currentBook}/advance?chars_read=${currentSection.chars_in_section}`, { method: 'POST' });
            await loadSection();
            // Auto-continue
            if (isPlaying && currentSection && !currentSection.done) {
                await playCurrentSection();
            } else {
                stopPlay();
            }
        };

        ttsAudio.play();
    } catch (e) {
        console.error('TTS failed:', e);
        stopPlay();
    }
}

// --- Summary ---
async function summarizeChapter() {
    if (!currentSection) return;
    const panel = document.getElementById('summaryPanel');
    const content = document.getElementById('summaryContent');

    panel.classList.add('active');
    document.getElementById('reader').style.display = 'none';
    content.innerHTML = '<div class="loading">Generating summary...</div>';

    try {
        const resp = await fetch(
            `${API}/reading/books/${currentBook}/chapters/${currentSection.chapter_index}/summarize`,
            { method: 'POST' }
        );
        const data = await resp.json();
        content.innerHTML = data.summary.replace(/\\n/g, '<br>').replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>');
    } catch (e) {
        content.innerHTML = '<p>Summary failed: ' + e.message + '</p>';
    }
}

function showSummary() {
    const panel = document.getElementById('summaryPanel');
    if (panel.classList.contains('active')) {
        panel.classList.remove('active');
        document.getElementById('reader').style.display = 'block';
    } else if (currentSection) {
        summarizeChapter();
    }
}

// --- Init ---
loadBooks();
</script>
</body>
</html>"""
