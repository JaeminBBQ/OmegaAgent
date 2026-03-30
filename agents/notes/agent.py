"""Note Agent — LangChain agent with Obsidian vault tools.

Default model: Claude Haiku (fast, affordable, reliable tool calling)
Escalation:    Claude Sonnet via ask_sonnet tool (complex reasoning)

Manages: work notes, work logs, todos, reminders, meeting notes,
         daily captures, weekly summaries, and planning.
"""

import logging
from datetime import datetime

from langchain_anthropic import ChatAnthropic
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from core.config import ANTHROPIC_API_KEY, OBSIDIAN_VAULT_PATH
from agents.notes.tools import ALL_TOOLS

logger = logging.getLogger(__name__)


def _build_system_prompt() -> str:
    """Build system prompt with current date/time (called fresh each request)."""
    now = datetime.now()
    return f"""You are OmegaAgent's note assistant. You help the user organize their
thoughts, tasks, work logs, and knowledge using an Obsidian vault at: {OBSIDIAN_VAULT_PATH}

CORE BEHAVIORS:
1. ALWAYS use your tools. Never just describe what you would do — actually do it.
2. Create well-organized markdown files with clear titles and structure.
3. Use Obsidian-compatible markdown (wikilinks [[note]], tags #tag, etc.)
4. Keep daily notes in /daily/YYYY-MM-DD.md
5. Keep general notes in /notes/
6. Keep tasks in /tasks/todo.md
7. Keep project notes in /projects/
8. Keep work logs in /work/YYYY-MM-DD.md
9. Keep meeting notes in /meetings/

CURRENT DATE AND TIME: {now.strftime('%Y-%m-%d %H:%M:%S')} ({now.strftime('%A')})

WORKFLOW FOR NOTES:
- When asked to take a note: vault_create or vault_append to the right file
- When asked to find something: vault_search first, then vault_view
- When asked to update: vault_view first to see current content, then vault_edit
- For daily notes: append to /daily/{now.strftime('%Y-%m-%d')}.md
- For quick thoughts: use quick_capture

WORKFLOW FOR TASKS:
- Use task_add, task_list, task_complete, task_remove
- Encourage the user to set priorities (high/medium/low)
- Proactively offer to organize or review tasks

WORKFLOW FOR WORK:
- Use work_log for quick work entries (auto-timestamped)
- Use work_standup for daily standup format (yesterday/today/blockers)
- Use meeting_notes for meeting notes with template
- Use weekly_summary to compile the past 7 days

WORKFLOW FOR REMINDERS:
- Use reminder_set(message, when) for all reminders
- ONE reminder:  reminder_set(message="Movie", when="4:30pm")
- MULTIPLE:      reminder_set(message="Movie;Mortgage", when="4:30pm;7pm")
  Separate each item and each time with a semicolon. Counts must match.
- CRITICAL: Pass the user's time words DIRECTLY. Do NOT calculate timestamps.
  "at 4:30" → '4:30pm'. "in 30 min" → '30m'. "tomorrow 9" → 'tomorrow 9am'.
- Use reminder_list to show upcoming, reminder_cancel to cancel
- Reminders notify via Discord webhook

WORKFLOW FOR PLANNING:
- Use ask_sonnet for complex planning, analysis, or summarization
- For project plans: create a file in /projects/ with structured sections
- Break large tasks into subtasks using task_add

Be concise but helpful. Speak naturally. If the user seems to be using voice,
keep responses short and conversational."""


class NoteAgent:
    """LangChain ReAct agent with Obsidian vault tools."""

    def __init__(self) -> None:
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is required for the note agent.")

        self._model = ChatAnthropic(
            model="claude-haiku-4-5",
            api_key=ANTHROPIC_API_KEY,
            temperature=0.0,
        )
        self._checkpointer = MemorySaver()
        self._agent = create_react_agent(
            model=self._model,
            tools=ALL_TOOLS,
            prompt=_build_system_prompt(),
            checkpointer=self._checkpointer,
        )
        self._thread_id = f"session-{datetime.now().strftime('%Y%m%d')}"
        logger.info("NoteAgent initialized (thread: %s)", self._thread_id)

    def reset(self) -> None:
        """Reset conversation memory and start a fresh session."""
        self._checkpointer = MemorySaver()
        self._agent = create_react_agent(
            model=self._model,
            tools=ALL_TOOLS,
            prompt=_build_system_prompt(),
            checkpointer=self._checkpointer,
        )
        self._thread_id = f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        logger.info("NoteAgent reset (thread: %s)", self._thread_id)

    async def chat(self, user_message: str, thread_id: str | None = None) -> str:
        """Send a message to the agent and return the response text.

        Args:
            user_message: The user's message.
            thread_id: Optional thread ID for multi-session support.

        Returns:
            The agent's text response.
        """
        now = datetime.now()
        timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
        stamped_message = f"[{timestamp}] {user_message}"

        config = {"configurable": {"thread_id": thread_id or self._thread_id}}
        result = await self._agent.ainvoke(
            {"messages": [{"role": "user", "content": stamped_message}]},
            config=config,
        )
        return result["messages"][-1].content
