"""Research Agent — web search and summarization with LangChain.

Default model: Claude Haiku (fast web research)
Escalation:    Claude Sonnet via ask_sonnet in note agent (if needed)

Capabilities: web search, news search, page fetching, save to vault.
"""

import logging
from datetime import datetime

from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from langgraph.checkpoint.memory import InMemorySaver

from core.config import ANTHROPIC_API_KEY
from agents.research.tools import ALL_TOOLS

logger = logging.getLogger(__name__)


def _build_system_prompt() -> str:
    """Build system prompt with current date/time."""
    now = datetime.now()
    return f"""You are OmegaAgent's research assistant. You help the user find information
on the web, summarize findings, and optionally save research to their Obsidian vault.

CURRENT DATE AND TIME: {now.strftime('%Y-%m-%d %H:%M:%S')} ({now.strftime('%A')})

CORE BEHAVIORS:
1. ALWAYS use your tools. Never make up facts — search first, then answer.
2. Synthesize results into clear, concise summaries.
3. Cite sources with URLs when providing information.
4. If the user asks to save/bookmark results, use save_research.

WORKFLOW:
- For factual questions: web_search → summarize the top results
- For current events: news_search → summarize with dates and sources
- For deep dives: web_search → fetch_page on the most relevant result → summarize
- For saving: save_research with a good title and formatted content

GUIDELINES:
- Keep summaries under 200 words unless the user asks for detail.
- Always mention your sources (title + URL).
- If search results are insufficient, try rephrasing the query.
- For technical topics, prefer official docs and reputable sources.
- Be direct. Don't pad responses with filler."""


class ResearchAgent:
    """LangChain agent with web research tools."""

    def __init__(self) -> None:
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is required for the research agent.")

        self._model = ChatAnthropic(
            model="claude-haiku-4-5",
            api_key=ANTHROPIC_API_KEY,
            temperature=0.0,
        )
        self._checkpointer = InMemorySaver()
        self._agent = create_agent(
            model=self._model,
            tools=ALL_TOOLS,
            system_prompt=_build_system_prompt(),
            checkpointer=self._checkpointer,
        )
        self._thread_id = f"research-{datetime.now().strftime('%Y%m%d')}"
        logger.info("ResearchAgent initialized (thread: %s)", self._thread_id)

    def reset(self) -> None:
        """Reset conversation memory."""
        self._checkpointer = InMemorySaver()
        self._agent = create_agent(
            model=self._model,
            tools=ALL_TOOLS,
            system_prompt=_build_system_prompt(),
            checkpointer=self._checkpointer,
        )
        self._thread_id = f"research-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        logger.info("ResearchAgent reset (thread: %s)", self._thread_id)

    async def chat(self, user_message: str, thread_id: str | None = None) -> str:
        """Send a message to the research agent and return the response.

        Args:
            user_message: The user's research question.
            thread_id: Optional thread ID for session continuity.

        Returns:
            The agent's text response with sources.
        """
        config = {"configurable": {"thread_id": thread_id or self._thread_id}}
        result = await self._agent.ainvoke(
            {"messages": [{"role": "user", "content": user_message}]},
            config=config,
        )
        return result["messages"][-1].content
