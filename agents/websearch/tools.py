"""Research agent tools — web search, news, page scraping, vault saving.

Uses the Serper API for search and httpx for page content retrieval.
Results can be saved to the Obsidian vault for later reference.
"""

import re
from datetime import datetime
from pathlib import Path

import httpx
from langchain_core.tools import tool

from core.config import OBSIDIAN_VAULT_PATH, SERPER_API_KEY

VAULT = Path(OBSIDIAN_VAULT_PATH).resolve()

SERPER_SEARCH_URL = "https://google.serper.dev/search"
SERPER_NEWS_URL = "https://google.serper.dev/news"


def _serper_headers() -> dict:
    if not SERPER_API_KEY:
        raise RuntimeError("SERPER_API_KEY is required for web search.")
    return {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}


@tool
def web_search(query: str, num_results: int = 5) -> str:
    """Search the web using Google via Serper API.

    Use this when you need current information, facts, documentation,
    or anything not in the user's vault.

    Args:
        query: The search query.
        num_results: Number of results to return (default 5, max 10).
    """
    num_results = min(num_results, 10)
    resp = httpx.post(
        SERPER_SEARCH_URL,
        json={"q": query, "num": num_results},
        headers=_serper_headers(),
        timeout=10.0,
    )
    resp.raise_for_status()
    data = resp.json()

    results = []
    # Knowledge graph / answer box
    if "answerBox" in data:
        ab = data["answerBox"]
        answer = ab.get("answer") or ab.get("snippet") or ab.get("title", "")
        if answer:
            results.append(f"**Quick Answer:** {answer}")

    # Organic results
    for item in data.get("organic", [])[:num_results]:
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        link = item.get("link", "")
        results.append(f"- **{title}**\n  {snippet}\n  {link}")

    if not results:
        return "No results found."

    return "\n\n".join(results)


@tool
def news_search(query: str, num_results: int = 5) -> str:
    """Search recent news articles via Serper.

    Use this when the user asks about current events, recent developments,
    or breaking news.

    Args:
        query: The news search query.
        num_results: Number of results (default 5, max 10).
    """
    num_results = min(num_results, 10)
    resp = httpx.post(
        SERPER_NEWS_URL,
        json={"q": query, "num": num_results},
        headers=_serper_headers(),
        timeout=10.0,
    )
    resp.raise_for_status()
    data = resp.json()

    results = []
    for item in data.get("news", [])[:num_results]:
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        link = item.get("link", "")
        source = item.get("source", "")
        date = item.get("date", "")
        results.append(f"- **{title}** ({source}, {date})\n  {snippet}\n  {link}")

    if not results:
        return "No news results found."

    return "\n\n".join(results)


@tool
def fetch_page(url: str) -> str:
    """Fetch and extract text content from a web page.

    Use this to read the full content of a specific URL found in search results.
    Returns the first ~3000 characters of visible text.

    Args:
        url: The URL to fetch.
    """
    try:
        resp = httpx.get(
            url,
            headers={"User-Agent": "OmegaAgent/1.0 (research assistant)"},
            timeout=15.0,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except Exception as e:
        return f"Failed to fetch page: {e}"

    text = resp.text
    # Strip HTML tags (simple approach)
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) > 3000:
        text = text[:3000] + "\n\n[...truncated]"

    return text if text else "Page content was empty."


@tool
def save_research(title: str, content: str, tags: str = "") -> str:
    """Save research findings to the Obsidian vault under /notes/research/.

    Use this when the user asks to save, bookmark, or keep research results.

    Args:
        title: Title for the research note.
        content: The research content to save (markdown formatted).
        tags: Optional comma-separated tags (e.g. "python,tutorial,web").
    """
    research_dir = VAULT / "notes" / "research"
    research_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    slug = re.sub(r"[^\w\s-]", "", title.lower()).replace(" ", "-")[:50]
    filename = f"{now.strftime('%Y-%m-%d')}-{slug}.md"
    path = research_dir / filename

    tag_line = ""
    if tags:
        tag_line = "\n" + " ".join(f"#{t.strip()}" for t in tags.split(",")) + "\n"

    note = f"# {title}\n\n*Researched: {now.strftime('%Y-%m-%d %H:%M')}*{tag_line}\n\n{content}\n"

    path.write_text(note)
    return f"Saved to notes/research/{filename}"


ALL_TOOLS = [
    web_search,
    news_search,
    fetch_page,
    save_research,
]
