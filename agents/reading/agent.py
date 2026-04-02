"""Reading Agent — helps the user read and study technical EPUB books.

Default model: Claude Haiku (summaries, key points, Q&A)
Escalation:    Claude Sonnet via ask_sonnet tool (complex analysis)

Manages: EPUB ingestion, chapter navigation, TTS narration, summaries,
         key point extraction, reading progress tracking.
"""

import logging
from datetime import datetime

from langchain_anthropic import ChatAnthropic
from langgraph.checkpoint.memory import InMemorySaver

from core.config import ANTHROPIC_API_KEY
from agents.reading.tools import ALL_TOOLS

logger = logging.getLogger(__name__)


def _build_system_prompt() -> str:
    """Build system prompt for the reading agent."""
    now = datetime.now()
    return f"""You are OmegaAgent's reading assistant. You help the user read, study, and
retain information from technical EPUB books (DevOps, software engineering, etc.).

CURRENT DATE AND TIME: {now.strftime('%Y-%m-%d %H:%M:%S')} ({now.strftime('%A')})

CORE BEHAVIORS:
1. ALWAYS use your tools to interact with books. Never make up content.
2. When asked to read or continue, use get_current_section to get text.
3. Track progress automatically — advance_position after each section.
4. Keep summaries concise and actionable for technical books.
5. Highlight practical takeaways, not just theory.

WORKFLOW FOR READING:
- "Continue reading" → get_current_section, return the text for TTS
- "What chapter am I on?" → get_reading_progress
- "Summarize this chapter" → get_chapter_text, then summarize it
- "Go to chapter 5" → set_chapter
- "What books do I have?" → list_books

WORKFLOW FOR SUMMARIES:
When summarizing a chapter, produce:
1. **TL;DR** — 1-2 sentence overview
2. **Key Points** — 3-5 bullet points of the most important ideas
3. **Key Terms** — Important terminology with brief definitions
4. **Practical Takeaways** — What should the reader actually do or remember

WORKFLOW FOR Q&A:
- If the user asks about something in the current chapter, use get_chapter_text
  to retrieve the full chapter, then answer from it.
- Be specific — cite sections or concepts from the text.

READING TIPS YOU SHOULD FOLLOW:
- When returning text for TTS, keep it clean — no markdown, no special chars.
- Break long sections into manageable chunks (~2-3 min of reading).
- At the end of each section, briefly note what's coming next.

Be concise and direct. The user is studying — respect their time."""


class ReadingAgent:
    """LangChain agent for reading and studying EPUB books."""

    def __init__(self) -> None:
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is required for the reading agent.")

        self._model = ChatAnthropic(
            model="claude-haiku-4-5",
            api_key=ANTHROPIC_API_KEY,
            temperature=0.0,
        )
        self._checkpointer = InMemorySaver()

        from langchain.agents import create_agent
        self._agent = create_agent(
            model=self._model,
            tools=ALL_TOOLS,
            system_prompt=_build_system_prompt(),
            checkpointer=self._checkpointer,
        )
        self._thread_id = f"reading-{datetime.now().strftime('%Y%m%d')}"
        logger.info("ReadingAgent initialized (thread: %s)", self._thread_id)

    def reset(self) -> None:
        """Reset conversation memory."""
        self._checkpointer = InMemorySaver()
        from langchain.agents import create_agent
        self._agent = create_agent(
            model=self._model,
            tools=ALL_TOOLS,
            system_prompt=_build_system_prompt(),
            checkpointer=self._checkpointer,
        )
        self._thread_id = f"reading-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        logger.info("ReadingAgent reset (thread: %s)", self._thread_id)

    async def chat(self, user_message: str, thread_id: str | None = None) -> str:
        """Send a message to the reading agent.

        Args:
            user_message: The user's message.
            thread_id: Optional thread ID for multi-session support.

        Returns:
            The agent's text response.
        """
        config = {"configurable": {"thread_id": thread_id or self._thread_id}}
        result = await self._agent.ainvoke(
            {"messages": [{"role": "user", "content": user_message}]},
            config=config,
        )
        return result["messages"][-1].content
