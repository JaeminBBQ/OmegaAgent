"""Chat route — general-purpose Haiku conversation endpoint."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

SYSTEM_PROMPT = """You are OmegaAgent, a personal AI assistant running on a home network.
You help with weather, scheduling, work tasks, and general questions.
Be concise and practical. If the user asks about weather, suggest they use the weather agent.
Keep responses under 200 words unless asked for detail."""


class ChatRequest(BaseModel):
    """Request body for chat."""

    message: str = Field(..., description="User message")
    system: str | None = Field(None, description="Optional system prompt override")
    max_tokens: int = Field(500, description="Max response tokens")


class ChatResponse(BaseModel):
    """Response from chat."""

    reply: str = Field(..., description="Assistant response")
    model: str = Field(..., description="Model used")


@router.post("/ask", response_model=ChatResponse)
async def ask(request: ChatRequest):
    """Send a message to Haiku and get a response.

    This is the general-purpose chat endpoint. RPi clients use this
    for freeform questions, task input, and anything that doesn't
    map to a specific agent.
    """
    from main import llm

    system = request.system or SYSTEM_PROMPT

    try:
        reply = await llm.ask(
            request.message,
            system=system,
            max_tokens=request.max_tokens,
        )
        return ChatResponse(reply=reply.strip(), model="claude-haiku-4-5")
    except Exception as exc:
        logger.error("Chat failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}")
