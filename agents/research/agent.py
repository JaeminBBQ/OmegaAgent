"""Research Agent — RAG over academic papers and research notes.

Uses Haiku for fast queries + Sonnet tool for advanced analysis.
"""

import logging
from typing import Optional

from langchain.agents import AgentExecutor, create_react_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import PromptTemplate

from core.config import ANTHROPIC_API_KEY
from core.llm import HAIKU

from .tools import ALL_TOOLS

logger = logging.getLogger(__name__)


class ResearchAgent:
    """Research assistant with RAG over papers and notes."""

    def __init__(self):
        """Initialize the research agent with Haiku + tools."""
        self.llm = ChatAnthropic(
            model=HAIKU,
            api_key=ANTHROPIC_API_KEY,
            temperature=0.1,
        )

        # System prompt for research agent
        self.system_prompt = """You are a research assistant helping with academic research.

You have access to:
- **search_papers**: Semantic search over uploaded research papers (PDFs)
- **search_research_notes**: Search Obsidian research notes
- **analyze_with_sonnet**: Use Claude Sonnet for advanced analysis (keywords, themes, synthesis, etc.)
- **cite_sources**: Format citations properly

When answering research questions:
1. Use search_papers to find relevant information from uploaded papers
2. Use search_research_notes to find your own research notes
3. For complex analysis tasks (extracting themes, identifying gaps, synthesizing findings), use analyze_with_sonnet
4. Always cite sources when referencing specific papers
5. Be precise and academic in your responses
6. If you don't find relevant information, say so clearly

Remember:
- Haiku (you) is fast and efficient for queries and coordination
- Sonnet is more capable for deep analysis - delegate complex reasoning to it via analyze_with_sonnet
- Always ground your answers in the retrieved sources"""

        # Create ReAct agent
        prompt = PromptTemplate.from_template(
            self.system_prompt + "\n\n{agent_scratchpad}\n\nQuestion: {input}\n\nThought:"
        )

        self.agent = create_react_agent(
            llm=self.llm,
            tools=ALL_TOOLS,
            prompt=prompt,
        )

        self.executor = AgentExecutor(
            agent=self.agent,
            tools=ALL_TOOLS,
            verbose=True,
            max_iterations=5,
            handle_parsing_errors=True,
        )

        logger.info("ResearchAgent initialized with %d tools", len(ALL_TOOLS))

    async def chat(self, message: str) -> str:
        """Process a research query.

        Args:
            message: User's research question

        Returns:
            Agent's response with citations
        """
        try:
            result = await self.executor.ainvoke({"input": message})
            return result["output"]
        except Exception as e:
            logger.error(f"Research agent error: {e}", exc_info=True)
            return f"I encountered an error processing your request: {e}"

    def reset(self):
        """Reset conversation memory."""
        # ReAct agent is stateless, but we can reinitialize if needed
        logger.info("Research agent reset (stateless)")
