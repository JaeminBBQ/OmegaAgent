"""Research agent tools — RAG retrieval + Sonnet-powered analysis.

Tools:
- search_papers: Semantic search over embedded paper chunks
- search_research_notes: Search Obsidian research notes
- analyze_with_sonnet: Advanced analysis using Claude Sonnet (keywords, themes, synthesis)
- cite_sources: Format citations properly
"""

import logging
from typing import List, Dict, Any

from langchain_core.tools import tool
from langchain_anthropic import ChatAnthropic

from core.config import ANTHROPIC_API_KEY
from core.embeddings import EmbeddingsClient
from core.research_db import ResearchDB

logger = logging.getLogger(__name__)

# Lazy-loaded clients
_sonnet = None
_embeddings = None
_research_db = None


def _get_sonnet():
    """Lazy load Sonnet model."""
    global _sonnet
    if _sonnet is None:
        _sonnet = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=ANTHROPIC_API_KEY,
            temperature=0.3,
        )
    return _sonnet


def _get_embeddings():
    """Lazy load embeddings client."""
    global _embeddings
    if _embeddings is None:
        _embeddings = EmbeddingsClient()
    return _embeddings


def _get_research_db():
    """Lazy load research DB client."""
    global _research_db
    if _research_db is None:
        _research_db = ResearchDB()
    return _research_db


@tool
async def search_papers(query: str, limit: int = 5) -> str:
    """Search academic papers using semantic similarity.
    
    Returns relevant paper chunks with metadata (title, authors, page).
    Use this to find information from uploaded research papers.
    
    Args:
        query: Search query (natural language question or keywords)
        limit: Max number of results (default 5)
    """
    try:
        embeddings_client = _get_embeddings()
        db = _get_research_db()
        
        # Generate query embedding
        query_embedding = await embeddings_client.embed_text(query)
        
        # Search papers
        results = await db.search_paper_chunks(
            query_embedding=query_embedding,
            threshold=0.7,
            limit=limit,
        )
        
        if not results:
            return "No relevant papers found for this query."
        
        # Format results
        formatted = []
        for i, result in enumerate(results, 1):
            title = result.get("paper_title", "Unknown")
            authors = result.get("paper_authors", [])
            content = result.get("chunk_content", "")
            page = result.get("page_number")
            similarity = result.get("similarity", 0)
            
            author_str = ", ".join(authors[:2]) if authors else "Unknown"
            if len(authors) > 2:
                author_str += " et al."
            
            page_str = f" (p. {page})" if page else ""
            
            formatted.append(
                f"{i}. **{title}** by {author_str}{page_str}\n"
                f"   Relevance: {similarity:.2f}\n"
                f"   {content[:300]}..."
            )
        
        return "\n\n".join(formatted)
        
    except Exception as e:
        logger.error(f"Paper search failed: {e}", exc_info=True)
        return f"Paper search error: {e}"


@tool
async def search_research_notes(query: str, limit: int = 5) -> str:
    """Search Obsidian research notes using semantic similarity.
    
    Returns relevant note excerpts from vault/notes/research/.
    Use this to find your own research notes and summaries.
    
    Args:
        query: Search query
        limit: Max number of results (default 5)
    """
    try:
        embeddings_client = _get_embeddings()
        db = _get_research_db()
        
        # Generate query embedding
        query_embedding = await embeddings_client.embed_text(query)
        
        # Search notes
        results = await db.search_research_notes(
            query_embedding=query_embedding,
            threshold=0.7,
            limit=limit,
        )
        
        if not results:
            return "No relevant research notes found for this query."
        
        # Format results
        formatted = []
        for i, result in enumerate(results, 1):
            title = result.get("note_title", "Untitled")
            content = result.get("note_content", "")
            file_path = result.get("file_path", "")
            similarity = result.get("similarity", 0)
            
            formatted.append(
                f"{i}. **{title}**\n"
                f"   File: {file_path}\n"
                f"   Relevance: {similarity:.2f}\n"
                f"   {content[:300]}..."
            )
        
        return "\n\n".join(formatted)
        
    except Exception as e:
        logger.error(f"Note search failed: {e}", exc_info=True)
        return f"Note search error: {e}"


@tool
async def analyze_with_sonnet(
    context: str,
    task: str = "extract_keywords",
) -> str:
    """Use Claude Sonnet for advanced research analysis.
    
    Sonnet is more capable than Haiku for complex reasoning tasks.
    Use this for:
    - Extracting key themes and concepts from papers
    - Identifying research gaps
    - Synthesizing findings across multiple sources
    - Generating research questions
    - Comparing methodologies
    
    Args:
        context: The text to analyze (paper excerpts, notes, etc.)
        task: Analysis task. Options:
            - "extract_keywords": Extract key terms and concepts
            - "identify_themes": Find main themes and patterns
            - "research_gaps": Identify gaps in current research
            - "synthesize": Synthesize findings across sources
            - "compare": Compare methodologies or approaches
            - "questions": Generate research questions
    
    Returns:
        Sonnet's analysis result
    """
    sonnet = _get_sonnet()
    
    task_prompts = {
        "extract_keywords": "Extract the key terms, concepts, and technical vocabulary from this text. Format as a bullet list with brief definitions.",
        "identify_themes": "Identify the main themes, patterns, and recurring ideas in this text. Explain each theme briefly.",
        "research_gaps": "Analyze this research and identify gaps, limitations, or areas that need further investigation.",
        "synthesize": "Synthesize the key findings and insights from this text. Create a coherent summary that connects the main ideas.",
        "compare": "Compare and contrast the methodologies, approaches, or findings presented in this text.",
        "questions": "Generate insightful research questions based on this text. Focus on questions that could advance the field.",
    }
    
    prompt_template = task_prompts.get(task, task_prompts["extract_keywords"])
    
    full_prompt = f"""{prompt_template}

TEXT TO ANALYZE:
{context}

Provide a clear, structured analysis. Be concise but thorough."""
    
    try:
        response = await sonnet.ainvoke(full_prompt)
        return response.content
    except Exception as e:
        logger.error(f"Sonnet analysis failed: {e}", exc_info=True)
        return f"Analysis failed: {e}"


@tool
def cite_sources(sources: List[Dict[str, Any]]) -> str:
    """Format paper citations in a standard format.
    
    Args:
        sources: List of source dicts with keys: title, authors, year, doi
        
    Returns:
        Formatted citations
    """
    if not sources:
        return "No sources to cite."
    
    citations = []
    for i, src in enumerate(sources, 1):
        title = src.get("title", "Unknown Title")
        authors = src.get("authors", ["Unknown"])
        year = src.get("year", "n.d.")
        doi = src.get("doi")
        
        # Format authors (Last, F.)
        if isinstance(authors, list):
            author_str = ", ".join(authors[:3])
            if len(authors) > 3:
                author_str += " et al."
        else:
            author_str = str(authors)
        
        citation = f"{i}. {author_str} ({year}). {title}."
        if doi:
            citation += f" https://doi.org/{doi}"
        
        citations.append(citation)
    
    return "\n".join(citations)


# Export all tools
ALL_TOOLS = [
    search_papers,
    search_research_notes,
    analyze_with_sonnet,
    cite_sources,
]
