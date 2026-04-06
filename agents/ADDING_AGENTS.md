# Adding an Agent or Tool to OmegaAgent

## Project Structure

```
agents/
├── notes/          # Note agent (vault, tasks, reminders, work logs)
│   ├── __init__.py
│   ├── agent.py    # NoteAgent class (LangChain create_agent)
│   └── tools.py    # 19 tools — vault CRUD, tasks, reminders, work, etc.
├── research/       # Research agent (web search, news, page fetch)
│   ├── __init__.py
│   ├── agent.py    # ResearchAgent class
│   └── tools.py    # 4 tools — web_search, news_search, fetch_page, save_research
├── weather/        # Weather agent (Open-Meteo API + Haiku summary)
│   ├── __init__.py
│   ├── agent.py    # WeatherAgent class (pipeline, not LangChain)
│   ├── api.py      # Open-Meteo API calls
│   └── models.py   # Pydantic models
└── ADDING_AGENTS.md
```

---

## Adding a Tool to an Existing Agent

Tools are the fastest way to extend functionality. Each tool is a decorated function in `tools.py`.

### 1. Define the tool

```python
# agents/notes/tools.py (or whichever agent)

from langchain_core.tools import tool

@tool
def my_new_tool(param: str) -> str:
    """One-line description shown to the LLM.

    Longer description of when/how to use this tool.

    Args:
        param: What this parameter does.
    """
    # Do the thing
    return "result string"
```

**Rules:**
- Use `@tool` from `langchain_core.tools`
- The docstring IS the tool description the LLM sees — make it clear
- Args must have type hints
- Return a string (the LLM reads the return value)
- Keep tools focused — one action per tool

### 2. Register it

Add the tool to `ALL_TOOLS` at the bottom of the file:

```python
ALL_TOOLS = [
    ...,
    my_new_tool,
]
```

The agent automatically picks it up on next restart. No other changes needed.

### 3. (Optional) Update the system prompt

If the tool needs specific usage instructions, add a workflow section in `agent.py`:

```python
# In _build_system_prompt()
WORKFLOW FOR MY_FEATURE:
- Use my_new_tool when the user asks about X
- Always do Y before calling it
```

---

## Adding a New Agent

### 1. Create the agent directory

```
mkdir agents/my_agent
```

### 2. Create tools.py

```python
# agents/my_agent/tools.py

from langchain_core.tools import tool

@tool
def do_something(query: str) -> str:
    """Description for the LLM."""
    return "result"

ALL_TOOLS = [do_something]
```

### 3. Create agent.py

```python
# agents/my_agent/agent.py

import logging
from datetime import datetime

from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from langgraph.checkpoint.memory import InMemorySaver

from core.config import ANTHROPIC_API_KEY
from agents.my_agent.tools import ALL_TOOLS

logger = logging.getLogger(__name__)


def _build_system_prompt() -> str:
    now = datetime.now()
    return f"""You are OmegaAgent's [purpose] assistant.

CURRENT DATE AND TIME: {now.strftime('%Y-%m-%d %H:%M:%S')} ({now.strftime('%A')})

CORE BEHAVIORS:
1. ALWAYS use your tools. Never describe what you would do — do it.
2. [Agent-specific instructions]

WORKFLOW:
- [When to use which tool]"""


class MyAgent:
    def __init__(self) -> None:
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is required.")

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
        self._thread_id = f"my-agent-{datetime.now().strftime('%Y%m%d')}"
        logger.info("MyAgent initialized (thread: %s)", self._thread_id)

    def reset(self) -> None:
        self._checkpointer = InMemorySaver()
        self._agent = create_agent(
            model=self._model,
            tools=ALL_TOOLS,
            system_prompt=_build_system_prompt(),
            checkpointer=self._checkpointer,
        )
        self._thread_id = f"my-agent-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    async def chat(self, user_message: str, thread_id: str | None = None) -> str:
        config = {"configurable": {"thread_id": thread_id or self._thread_id}}
        result = await self._agent.ainvoke(
            {"messages": [{"role": "user", "content": user_message}]},
            config=config,
        )
        return result["messages"][-1].content
```

### 4. Create __init__.py

```python
# agents/my_agent/__init__.py
from agents.my_agent.agent import MyAgent
__all__ = ["MyAgent"]
```

### 5. Add API route

```python
# api/routes/my_agent.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/my-agent", tags=["my-agent"])


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    thread_id: str


@router.post("/chat", response_model=ChatResponse)
async def my_agent_chat(request: ChatRequest):
    from main import my_agent

    try:
        reply = await my_agent.chat(request.message, thread_id=request.thread_id)
        return ChatResponse(reply=reply, thread_id=request.thread_id or my_agent._thread_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
```

### 6. Wire into main.py

```python
# Add import
from api.routes.my_agent import router as my_agent_router

# Add router
app.include_router(my_agent_router)

# Add instance
from agents.my_agent import MyAgent
my_agent = MyAgent()
```

### 7. Add client method in omega_client.py

```python
async def my_agent_chat(self, message: str, thread_id: str | None = None) -> str:
    host = await self._get_host()
    payload: dict = {"message": message}
    if thread_id:
        payload["thread_id"] = thread_id
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{host}/my-agent/chat", json=payload)
        r.raise_for_status()
        return r.json()["reply"]
```

### 8. Add command in rpi400_assistant.py (if applicable)

Add to `HELP_TEXT`, add a handler function, and add the command to the main loop.

---

## Key Dependencies

| Package | Import | Used For |
|---------|--------|----------|
| `langchain` | `from langchain.agents import create_agent` | Agent orchestration |
| `langchain_core` | `from langchain_core.tools import tool` | Tool decorator |
| `langchain_anthropic` | `from langchain_anthropic import ChatAnthropic` | Claude models |
| `langgraph` | `from langgraph.checkpoint.memory import InMemorySaver` | Conversation memory |

## Tips

- **Haiku** (`claude-haiku-4-5`) handles up to ~64 tools. Keep it under 20 per agent for best results.
- Tools must return **strings**. The LLM reads the return value as context.
- Use `_build_system_prompt()` as a function (not a constant) so it gets fresh datetime on each call.
- The `InMemorySaver` checkpointer resets on container restart. That's fine for most agents.
- If your agent needs env vars, add them to `core/config.py` and `.env.example`.
