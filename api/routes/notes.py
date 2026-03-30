"""Note agent routes — conversational note-taking with tool use."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notes", tags=["notes"])


class NoteChatRequest(BaseModel):
    """Request body for note agent chat."""

    message: str = Field(..., description="User message")
    thread_id: str | None = Field(None, description="Optional thread ID for session continuity")


class NoteChatResponse(BaseModel):
    """Response from note agent chat."""

    reply: str = Field(..., description="Agent response")
    thread_id: str = Field(..., description="Thread ID used")


class QuickTaskRequest(BaseModel):
    """Quick task add without conversational overhead."""

    description: str = Field(..., description="Task description")
    priority: str = Field("medium", description="high, medium, or low")


class QuickReminderRequest(BaseModel):
    """Quick reminder set without conversational overhead."""

    message: str = Field(..., description="Reminder message (semicolons for multiple)")
    when: str = Field(..., description="Time expression (semicolons for multiple)")


class QuickNoteRequest(BaseModel):
    """Quick note capture."""

    text: str = Field(..., description="Note text to capture")


class QuickWorkLogRequest(BaseModel):
    """Quick work log entry."""

    entry: str = Field(..., description="Work log entry")


@router.post("/chat", response_model=NoteChatResponse)
async def note_chat(request: NoteChatRequest):
    """Conversational note-taking — the agent uses tools to manage your vault.

    Supports multi-turn conversation. Send a thread_id to continue
    a previous session, or omit for the default daily session.
    """
    from main import note_agent

    try:
        reply = await note_agent.chat(
            request.message,
            thread_id=request.thread_id,
        )
        return NoteChatResponse(
            reply=reply,
            thread_id=request.thread_id or note_agent._thread_id,
        )
    except Exception as exc:
        logger.error("Note chat failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Note agent error: {exc}")


@router.post("/task")
async def quick_task(request: QuickTaskRequest):
    """Add a task directly without going through the conversational agent."""
    from agents.notes.tools import task_add

    result = task_add.invoke({"description": request.description, "priority": request.priority})
    return {"result": result}


@router.post("/remind")
async def quick_remind(request: QuickReminderRequest):
    """Set a reminder directly without going through the conversational agent."""
    from agents.notes.tools import reminder_set

    result = reminder_set.invoke({"message": request.message, "when": request.when})
    return {"result": result}


@router.post("/capture")
async def quick_note(request: QuickNoteRequest):
    """Quick-capture a note to today's daily file."""
    from agents.notes.tools import quick_capture

    result = quick_capture.invoke({"text": request.text})
    return {"result": result}


@router.post("/worklog")
async def quick_worklog(request: QuickWorkLogRequest):
    """Add a work log entry directly."""
    from agents.notes.tools import work_log

    result = work_log.invoke({"entry": request.entry})
    return {"result": result}


@router.get("/tasks")
async def list_tasks():
    """List all pending tasks."""
    from agents.notes.tools import task_list

    result = task_list.invoke({"show_completed": False})
    return {"result": result}


@router.get("/reminders")
async def list_reminders():
    """List all upcoming reminders."""
    from agents.notes.tools import reminder_list

    result = reminder_list.invoke({"show_delivered": False})
    return {"result": result}


@router.post("/reset")
async def reset_session():
    """Reset the note agent conversation memory."""
    from main import note_agent

    note_agent.reset()
    return {"result": "Session reset. Starting fresh."}
