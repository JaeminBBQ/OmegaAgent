"""WebSearch agent API routes."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/websearch", tags=["websearch"])


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
    from main import websearch_agent

    try:
        reply = await websearch_agent.chat(
            request.message,
            thread_id=request.thread_id,
        )
        return ResearchChatResponse(
            reply=reply,
            thread_id=request.thread_id or websearch_agent._thread_id,
        )
    except Exception as exc:
        logger.error("WebSearch chat failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"WebSearch agent error: {exc}")


@router.post("/reset")
async def reset_session():
    """Reset the websearch agent conversation memory."""
    from main import websearch_agent

    websearch_agent.reset()
    return {"result": "WebSearch session reset."}
