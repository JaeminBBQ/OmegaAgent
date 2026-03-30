"""Research agent routes — web search and summarization."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/research", tags=["research"])


class ResearchChatRequest(BaseModel):
    """Request body for research agent chat."""

    message: str = Field(..., description="Research question or query")
    thread_id: str | None = Field(None, description="Optional thread ID for session continuity")


class ResearchChatResponse(BaseModel):
    """Response from research agent."""

    reply: str = Field(..., description="Agent response with sources")
    thread_id: str = Field(..., description="Thread ID used")


@router.post("/chat", response_model=ResearchChatResponse)
async def research_chat(request: ResearchChatRequest):
    """Ask the research agent to search the web and summarize findings.

    Supports multi-turn conversation for follow-up questions.
    """
    from main import research_agent

    try:
        reply = await research_agent.chat(
            request.message,
            thread_id=request.thread_id,
        )
        return ResearchChatResponse(
            reply=reply,
            thread_id=request.thread_id or research_agent._thread_id,
        )
    except Exception as exc:
        logger.error("Research chat failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Research agent error: {exc}")


@router.post("/reset")
async def reset_session():
    """Reset the research agent conversation memory."""
    from main import research_agent

    research_agent.reset()
    return {"result": "Research session reset."}
