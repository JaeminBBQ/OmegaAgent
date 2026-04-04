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

logger = logging.getLogger(__name__)

# Sonnet model for advanced analysis
_sonnet = None


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


@tool
async def search_papers(query: str, limit: int = 5) -> str:
    """Search academic papers using semantic similarity.
    
    Returns relevant paper chunks with metadata (title, authors, page).
    Use this to find information from uploaded research papers.
    
    Args:
        query: Search query (natural language question or keywords)
        limit: Max number of results (default 5)
    """
    # TODO: Implement RAG retrieval from Supabase
    # For now, return placeholder
    return f"[Paper search not yet implemented. Query: {query}]"


@tool
async def search_research_notes(query: str, limit: int = 5) -> str:
    """Search Obsidian research notes using semantic similarity.
    
    Returns relevant note excerpts from vault/notes/research/.
    Use this to find your own research notes and summaries.
    
    Args:
        query: Search query
        limit: Max number of results (default 5)
    """
    # TODO: Implement note search from Obsidian vault
    return f"[Note search not yet implemented. Query: {query}]"


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
