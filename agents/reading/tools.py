"""Reading assistant tools — EPUB ingestion, chapter extraction, progress, summaries."""

import json
import logging
import os
import re
from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _books_dir() -> Path:
    """Return the books storage directory, creating it if needed."""
    d = Path(os.getenv("BOOKS_DIR", "./books"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _book_dir(book_id: str) -> Path:
    """Return the directory for a specific book."""
    return _books_dir() / book_id


def _sanitize_id(name: str) -> str:
    """Convert a book title to a filesystem-safe ID."""
    return re.sub(r"[^\w-]", "_", name.lower().strip())[:80]


def _extract_text_from_html(html: str) -> str:
    """Convert HTML content to clean plain text."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove script and style elements
    for tag in soup(["script", "style"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def _load_metadata(book_id: str) -> dict | None:
    """Load book metadata from disk."""
    meta_path = _book_dir(book_id) / "metadata.json"
    if not meta_path.exists():
        return None
    return json.loads(meta_path.read_text())


def _save_metadata(book_id: str, metadata: dict) -> None:
    """Save book metadata to disk."""
    meta_path = _book_dir(book_id) / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2))


def _load_progress(book_id: str) -> dict:
    """Load reading progress for a book."""
    prog_path = _book_dir(book_id) / "progress.json"
    if prog_path.exists():
        return json.loads(prog_path.read_text())
    return {"chapter_index": 0, "position": 0, "completed_chapters": []}


def _save_progress(book_id: str, progress: dict) -> None:
    """Save reading progress for a book."""
    prog_path = _book_dir(book_id) / "progress.json"
    prog_path.write_text(json.dumps(progress, indent=2))


# ---------------------------------------------------------------------------
# EPUB Ingestion
# ---------------------------------------------------------------------------

def ingest_epub_file(file_path: str | Path) -> dict:
    """Parse an EPUB file into chapters and store on disk.

    Returns metadata dict with book_id, title, author, chapter_count.
    """
    file_path = Path(file_path)
    book = epub.read_epub(str(file_path))

    # Extract metadata
    title = book.get_metadata("DC", "title")
    title = title[0][0] if title else file_path.stem
    author = book.get_metadata("DC", "creator")
    author = author[0][0] if author else "Unknown"

    book_id = _sanitize_id(title)
    book_path = _book_dir(book_id)
    book_path.mkdir(parents=True, exist_ok=True)
    chapters_dir = book_path / "chapters"
    chapters_dir.mkdir(exist_ok=True)
    summaries_dir = book_path / "summaries"
    summaries_dir.mkdir(exist_ok=True)

    # Extract chapters from spine order
    chapters = []
    spine_ids = [item_id for item_id, _ in book.spine]
    items_by_id = {item.get_id(): item for item in book.get_items()}

    chapter_index = 0
    for item_id in spine_ids:
        item = items_by_id.get(item_id)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue

        html_content = item.get_content().decode("utf-8", errors="replace")
        text = _extract_text_from_html(html_content)

        # Skip very short sections (TOC, copyright, etc.)
        if len(text.strip()) < 200:
            continue

        # Try to extract chapter title from first heading
        soup = BeautifulSoup(html_content, "html.parser")
        heading = soup.find(["h1", "h2", "h3"])
        chapter_title = heading.get_text().strip() if heading else f"Section {chapter_index + 1}"

        chapters.append({
            "index": chapter_index,
            "title": chapter_title,
            "word_count": len(text.split()),
        })

        # Save chapter text
        chapter_file = chapters_dir / f"{chapter_index:03d}.txt"
        chapter_file.write_text(text)
        chapter_index += 1

    metadata = {
        "book_id": book_id,
        "title": title,
        "author": author,
        "chapter_count": len(chapters),
        "chapters": chapters,
        "total_words": sum(c["word_count"] for c in chapters),
    }
    _save_metadata(book_id, metadata)
    _save_progress(book_id, {"chapter_index": 0, "position": 0, "completed_chapters": []})

    logger.info("Ingested '%s' by %s: %d chapters, %d words",
                title, author, len(chapters), metadata["total_words"])
    return metadata


# ---------------------------------------------------------------------------
# LangChain Tools
# ---------------------------------------------------------------------------

@tool
def list_books() -> str:
    """List all ingested books with their reading progress."""
    books_dir = _books_dir()
    results = []
    for meta_file in sorted(books_dir.glob("*/metadata.json")):
        meta = json.loads(meta_file.read_text())
        progress = _load_progress(meta["book_id"])
        pct = 0
        if meta["chapter_count"] > 0:
            pct = int(len(progress.get("completed_chapters", [])) / meta["chapter_count"] * 100)
        results.append(
            f"- **{meta['title']}** by {meta['author']} "
            f"({meta['chapter_count']} chapters, {meta['total_words']:,} words) "
            f"— {pct}% complete (ch {progress['chapter_index'] + 1}/{meta['chapter_count']})"
        )
    return "\n".join(results) if results else "No books ingested yet."


@tool
def get_chapters(book_id: str) -> str:
    """List all chapters for a book.

    Args:
        book_id: The book identifier.
    """
    meta = _load_metadata(book_id)
    if not meta:
        return f"Book not found: {book_id}"

    progress = _load_progress(book_id)
    lines = [f"**{meta['title']}** — Chapters:\n"]
    for ch in meta["chapters"]:
        marker = "✓" if ch["index"] in progress.get("completed_chapters", []) else " "
        current = " ←" if ch["index"] == progress["chapter_index"] else ""
        lines.append(f"  [{marker}] {ch['index'] + 1}. {ch['title']} ({ch['word_count']:,} words){current}")
    return "\n".join(lines)


@tool
def get_chapter_text(book_id: str, chapter_index: int) -> str:
    """Get the full text of a specific chapter.

    Args:
        book_id: The book identifier.
        chapter_index: Zero-based chapter index.
    """
    chapter_file = _book_dir(book_id) / "chapters" / f"{chapter_index:03d}.txt"
    if not chapter_file.exists():
        return f"Chapter {chapter_index} not found for book {book_id}"
    return chapter_file.read_text()


@tool
def get_current_section(book_id: str, max_chars: int = 3000) -> str:
    """Get the current reading section based on progress.

    Returns a chunk of text from the current position, suitable for TTS.

    Args:
        book_id: The book identifier.
        max_chars: Maximum characters to return (default 3000 ≈ 2-3 min TTS).
    """
    meta = _load_metadata(book_id)
    if not meta:
        return f"Book not found: {book_id}"

    progress = _load_progress(book_id)
    ch_idx = progress["chapter_index"]
    position = progress.get("position", 0)

    chapter_file = _book_dir(book_id) / "chapters" / f"{ch_idx:03d}.txt"
    if not chapter_file.exists():
        return "No more chapters to read."

    text = chapter_file.read_text()
    section = text[position:position + max_chars]

    # Try to end at a sentence boundary
    if position + max_chars < len(text):
        last_period = section.rfind(". ")
        if last_period > max_chars * 0.5:
            section = section[:last_period + 1]

    ch_title = meta["chapters"][ch_idx]["title"] if ch_idx < len(meta["chapters"]) else f"Chapter {ch_idx + 1}"
    header = f"[{meta['title']} — {ch_title}]\n\n"
    return header + section


@tool
def advance_position(book_id: str, chars_read: int) -> str:
    """Advance the reading position after TTS playback.

    Args:
        book_id: The book identifier.
        chars_read: Number of characters that were read/played.
    """
    meta = _load_metadata(book_id)
    if not meta:
        return f"Book not found: {book_id}"

    progress = _load_progress(book_id)
    ch_idx = progress["chapter_index"]

    chapter_file = _book_dir(book_id) / "chapters" / f"{ch_idx:03d}.txt"
    if not chapter_file.exists():
        return "Already at end of book."

    chapter_len = len(chapter_file.read_text())
    new_position = progress.get("position", 0) + chars_read

    if new_position >= chapter_len:
        # Chapter complete — move to next
        completed = progress.get("completed_chapters", [])
        if ch_idx not in completed:
            completed.append(ch_idx)
        progress["completed_chapters"] = completed
        progress["chapter_index"] = ch_idx + 1
        progress["position"] = 0

        if ch_idx + 1 >= meta["chapter_count"]:
            _save_progress(book_id, progress)
            return f"Book complete! Finished all {meta['chapter_count']} chapters."

        next_title = meta["chapters"][ch_idx + 1]["title"]
        _save_progress(book_id, progress)
        return f"Chapter complete! Next: {next_title}"
    else:
        progress["position"] = new_position
        _save_progress(book_id, progress)
        pct = int(new_position / chapter_len * 100)
        return f"Position updated: {pct}% through current chapter."


@tool
def get_reading_progress(book_id: str) -> str:
    """Get detailed reading progress for a book.

    Args:
        book_id: The book identifier.
    """
    meta = _load_metadata(book_id)
    if not meta:
        return f"Book not found: {book_id}"

    progress = _load_progress(book_id)
    ch_idx = progress["chapter_index"]
    completed = len(progress.get("completed_chapters", []))
    total = meta["chapter_count"]

    chapter_file = _book_dir(book_id) / "chapters" / f"{ch_idx:03d}.txt"
    ch_pct = 0
    if chapter_file.exists():
        ch_len = len(chapter_file.read_text())
        if ch_len > 0:
            ch_pct = int(progress.get("position", 0) / ch_len * 100)

    ch_title = meta["chapters"][ch_idx]["title"] if ch_idx < len(meta["chapters"]) else "Finished"

    return (
        f"**{meta['title']}**\n"
        f"Progress: {completed}/{total} chapters ({int(completed/total*100)}%)\n"
        f"Current: {ch_title} ({ch_pct}% through)\n"
        f"Total words: {meta['total_words']:,}"
    )


@tool
def set_chapter(book_id: str, chapter_index: int) -> str:
    """Jump to a specific chapter.

    Args:
        book_id: The book identifier.
        chapter_index: Zero-based chapter index to jump to.
    """
    meta = _load_metadata(book_id)
    if not meta:
        return f"Book not found: {book_id}"
    if chapter_index < 0 or chapter_index >= meta["chapter_count"]:
        return f"Invalid chapter index. Book has {meta['chapter_count']} chapters (0-{meta['chapter_count']-1})."

    progress = _load_progress(book_id)
    progress["chapter_index"] = chapter_index
    progress["position"] = 0
    _save_progress(book_id, progress)

    ch_title = meta["chapters"][chapter_index]["title"]
    return f"Jumped to chapter {chapter_index + 1}: {ch_title}"


# All tools for the reading agent
ALL_TOOLS = [
    list_books,
    get_chapters,
    get_chapter_text,
    get_current_section,
    advance_position,
    get_reading_progress,
    set_chapter,
]
