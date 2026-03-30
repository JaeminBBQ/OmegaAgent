"""Note agent tools — Obsidian vault CRUD, tasks, reminders, work tools.

Ported from homeagent/note-assistant with additions for:
- Work logs (daily standup format)
- Meeting notes (templated)
- Weekly summaries
- Quick capture (auto-categorized)
"""

import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import requests
from langchain_core.tools import tool

from core.config import OBSIDIAN_VAULT_PATH, DISCORD_WEBHOOK_URL

VAULT = Path(OBSIDIAN_VAULT_PATH).resolve()

# ── Helpers ──────────────────────────────────────────────────────────


def _validate_path(path: str) -> Path:
    """Resolve path within vault and prevent directory traversal."""
    full_path = (VAULT / path.lstrip("/")).resolve()
    try:
        full_path.relative_to(VAULT.resolve())
    except ValueError:
        raise ValueError("Access denied: path outside vault directory")
    return full_path


def _ensure_vault():
    """Create vault and default folders if they don't exist."""
    for folder in ["daily", "notes", "tasks", "projects", "work", "meetings", "templates"]:
        (VAULT / folder).mkdir(parents=True, exist_ok=True)


# ── Vault CRUD ───────────────────────────────────────────────────────


@tool
def vault_view(path: str) -> str:
    """View a file or list a directory in the Obsidian vault.

    Args:
        path: Path relative to vault root, e.g. '/' or '/notes' or '/notes/idea.md'
    """
    _ensure_vault()
    full_path = _validate_path(path)
    if not full_path.exists():
        return f"Path '{path}' does not exist."
    if full_path.is_dir():
        items = sorted(full_path.iterdir())
        if not items:
            return f"Directory '{path}' is empty."
        listing = []
        for item in items:
            prefix = "📁" if item.is_dir() else "📄"
            listing.append(f"  {prefix} {item.name}")
        return f"Contents of {path}:\n" + "\n".join(listing)
    else:
        content = full_path.read_text()
        return f"--- {path} ---\n{content}"


@tool
def vault_create(path: str, content: str) -> str:
    """Create a new .md file in the Obsidian vault.

    Args:
        path: File path, e.g. '/notes/meeting-notes.md'
        content: Markdown content to write.
    """
    _ensure_vault()
    full_path = _validate_path(path)
    full_path.parent.mkdir(parents=True, exist_ok=True)
    if full_path.exists():
        return f"File '{path}' already exists. Use vault_edit or vault_append to modify it."
    full_path.write_text(content)
    return f"Created '{path}' ({len(content)} chars)"


@tool
def vault_edit(path: str, old_text: str, new_text: str) -> str:
    """Edit an existing file by replacing text.

    Args:
        path: File path to edit.
        old_text: Exact text to find.
        new_text: Replacement text.
    """
    full_path = _validate_path(path)
    if not full_path.exists():
        return f"File '{path}' does not exist."
    content = full_path.read_text()
    if old_text not in content:
        return f"Text not found in '{path}'. Use vault_view to see current contents."
    new_content = content.replace(old_text, new_text, 1)
    full_path.write_text(new_content)
    return f"Updated '{path}'"


@tool
def vault_append(path: str, content: str) -> str:
    """Append content to an existing file. Creates the file if it doesn't exist.

    Args:
        path: File path, e.g. '/daily/2024-01-15.md'
        content: Markdown content to append.
    """
    _ensure_vault()
    full_path = _validate_path(path)
    full_path.parent.mkdir(parents=True, exist_ok=True)
    with open(full_path, "a") as f:
        f.write(content)
    return f"Appended to '{path}' ({len(content)} chars)"


@tool
def vault_delete(path: str) -> str:
    """Delete a file or directory from the vault.

    Args:
        path: Path to delete.
    """
    full_path = _validate_path(path)
    if not full_path.exists():
        return f"Path '{path}' does not exist."
    if full_path.is_dir():
        shutil.rmtree(full_path)
        return f"Deleted directory '{path}'"
    else:
        full_path.unlink()
        return f"Deleted file '{path}'"


@tool
def vault_search(query: str) -> str:
    """Search all .md files in the vault for a keyword.

    Args:
        query: Search term (case-insensitive).
    """
    _ensure_vault()
    results = []
    for md_file in VAULT.rglob("*.md"):
        content = md_file.read_text()
        if query.lower() in content.lower():
            rel_path = md_file.relative_to(VAULT)
            for line in content.splitlines():
                if query.lower() in line.lower():
                    results.append(f"  📄 /{rel_path}: {line.strip()[:120]}")
                    break
    if not results:
        return f"No results for '{query}'."
    return f"Found {len(results)} match(es):\n" + "\n".join(results[:20])


# ── Task tools ───────────────────────────────────────────────────────

TASKS_FILE = "tasks/todo.md"


def _get_tasks_path() -> Path:
    path = VAULT / TASKS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        header = f"# Tasks\n\nLast updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        path.write_text(header)
    return path


def _parse_tasks(content: str) -> list[dict]:
    tasks = []
    for i, line in enumerate(content.splitlines()):
        stripped = line.strip()
        if stripped.startswith("- [ ] "):
            tasks.append({"index": i, "text": stripped[6:], "done": False, "raw": line})
        elif stripped.startswith("- [x] "):
            tasks.append({"index": i, "text": stripped[6:], "done": True, "raw": line})
    return tasks


@tool
def task_add(description: str, priority: str = "medium") -> str:
    """Add a new task to the todo list.

    Args:
        description: What needs to be done.
        priority: Priority level — 'high', 'medium', or 'low'.
    """
    path = _get_tasks_path()
    tag = f"#{priority}" if priority in ("high", "medium", "low") else "#medium"
    task_line = f"- [ ] {tag} {description}\n"
    with open(path, "a") as f:
        f.write(task_line)

    content = path.read_text()
    if "Last updated:" in content:
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if "Last updated:" in line:
                lines[i] = f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                break
        path.write_text("\n".join(lines) + "\n")

    return f"Added task: {tag} {description}"


@tool
def task_list(show_completed: bool = False) -> str:
    """List all tasks from the todo list.

    Args:
        show_completed: Whether to include completed tasks.
    """
    path = _get_tasks_path()
    content = path.read_text()
    tasks = _parse_tasks(content)

    if not tasks:
        return "No tasks found. Use task_add to create one."

    pending = [t for t in tasks if not t["done"]]
    completed = [t for t in tasks if t["done"]]

    lines = []
    if pending:
        lines.append(f"📋 Pending ({len(pending)}):")
        for t in pending:
            lines.append(f"  - [ ] {t['text']}")
    else:
        lines.append("✅ No pending tasks!")

    if show_completed and completed:
        lines.append(f"\n✅ Completed ({len(completed)}):")
        for t in completed:
            lines.append(f"  - [x] {t['text']}")

    return "\n".join(lines)


@tool
def task_complete(task_text: str) -> str:
    """Mark a task as complete by matching its description.

    Args:
        task_text: Partial or full text of the task to complete.
    """
    path = _get_tasks_path()
    content = path.read_text()
    lines = content.splitlines()

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("- [ ] ") and task_text.lower() in stripped.lower():
            lines[i] = line.replace("- [ ] ", "- [x] ", 1)
            path.write_text("\n".join(lines) + "\n")
            return f"Completed: {stripped[6:]}"

    return f"No pending task matching '{task_text}' found."


@tool
def task_remove(task_text: str) -> str:
    """Remove a task entirely from the list.

    Args:
        task_text: Partial or full text of the task to remove.
    """
    path = _get_tasks_path()
    content = path.read_text()
    lines = content.splitlines()

    for i, line in enumerate(lines):
        stripped = line.strip()
        if (stripped.startswith("- [ ] ") or stripped.startswith("- [x] ")) and \
           task_text.lower() in stripped.lower():
            removed = lines.pop(i)
            path.write_text("\n".join(lines) + "\n")
            return f"Removed: {stripped}"

    return f"No task matching '{task_text}' found."


# ── Reminder tools ───────────────────────────────────────────────────

REMINDERS_FILE = "tasks/reminders.md"


def _get_reminders_path() -> Path:
    path = VAULT / REMINDERS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("# Reminders\n\n")
    return path


def _parse_reminders(content: str) -> list[dict]:
    reminders = []
    for i, line in enumerate(content.splitlines()):
        stripped = line.strip()
        if stripped.startswith("- [ ] ") or stripped.startswith("- [x] "):
            done = stripped.startswith("- [x] ")
            body = stripped[6:]
            if " | " in body:
                dt_str, message = body.split(" | ", 1)
                reminders.append({
                    "index": i,
                    "datetime_str": dt_str.strip(),
                    "message": message.strip(),
                    "done": done,
                    "raw": line,
                })
    return reminders


def _send_discord(message: str) -> bool:
    if not DISCORD_WEBHOOK_URL or DISCORD_WEBHOOK_URL.startswith("https://discord.com/api/webhooks/your"):
        return False
    try:
        payload = {
            "content": f"⏰ **Reminder:** {message}",
            "username": "OmegaAgent",
        }
        resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception:
        return False


def check_and_fire_reminders() -> int:
    """Check for due reminders and fire them. Called by APScheduler."""
    path = _get_reminders_path()
    content = path.read_text()
    lines = content.splitlines()
    now = datetime.now()
    fired = 0

    for reminder in _parse_reminders(content):
        if reminder["done"]:
            continue
        try:
            remind_at = datetime.strptime(reminder["datetime_str"], "%Y-%m-%d %H:%M")
        except ValueError:
            continue

        if now >= remind_at:
            sent = _send_discord(reminder["message"])
            status = "delivered" if sent else "fired, no webhook"
            old_line = reminder["raw"]
            new_line = old_line.replace("- [ ] ", "- [x] ", 1)
            if not new_line.endswith(f"({status})"):
                new_line = f"{new_line} ({status})"
            lines[reminder["index"]] = new_line
            fired += 1

    if fired:
        path.write_text("\n".join(lines) + "\n")
    return fired


def _parse_when(when: str) -> datetime | None:
    """Parse a wide variety of time expressions into an absolute datetime."""
    when = when.strip()
    now = datetime.now()

    try:
        return datetime.strptime(when, "%Y-%m-%d %H:%M")
    except ValueError:
        pass

    rel_match = re.fullmatch(r'(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?', when.lower())
    if rel_match and any(rel_match.groups()):
        days = int(rel_match.group(1) or 0)
        hours = int(rel_match.group(2) or 0)
        minutes = int(rel_match.group(3) or 0)
        return now + timedelta(days=days, hours=hours, minutes=minutes)

    lower = when.lower().strip()
    day_offset = 0
    for prefix in ("tomorrow", "tmrw"):
        if lower.startswith(prefix):
            day_offset = 1
            lower = lower[len(prefix):].strip()
            break
    if lower.startswith("today"):
        lower = lower[5:].strip()

    clock_match = re.fullmatch(
        r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', lower, re.IGNORECASE
    )
    if clock_match:
        hour = int(clock_match.group(1))
        minute = int(clock_match.group(2) or 0)
        ampm = (clock_match.group(3) or "").lower()

        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0

        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        target += timedelta(days=day_offset)

        if day_offset == 0 and target <= now:
            target += timedelta(days=1)

        return target

    return None


def _create_single_reminder(message: str, when: str) -> str:
    remind_at = _parse_when(when)
    if remind_at is None:
        return f"Could not parse time '{when}' for: {message}"

    dt_str = remind_at.strftime("%Y-%m-%d %H:%M")
    line = f"- [ ] {dt_str} | {message}\n"

    path = _get_reminders_path()
    with open(path, "a") as f:
        f.write(line)

    return f"✓ {dt_str} — {message}"


@tool
def reminder_set(message: str, when: str) -> str:
    """Set one or more reminders. Notifies via Discord at the specified time(s).

    IMPORTANT: Pass the user's time words directly. Do NOT do any time math.

    For ONE reminder:
        reminder_set(message="Movie", when="4:30pm")

    For MULTIPLE reminders, separate with semicolons:
        reminder_set(message="Movie;Mortgage paperwork", when="4:30pm;7pm")

    Args:
        message: What to be reminded about. Use semicolons to separate multiple items.
        when: Time expression(s). Use semicolons to separate if multiple.
              Valid formats: '4:30pm', '10m', '1h', 'tomorrow 9am', '2026-03-24 16:30'
    """
    messages = [m.strip() for m in message.split(";") if m.strip()]
    times = [t.strip() for t in when.split(";") if t.strip()]

    if len(times) == 1 and len(messages) > 1:
        times = times * len(messages)

    if len(messages) != len(times):
        return (
            f"Mismatch: {len(messages)} message(s) but {len(times)} time(s). "
            f"Separate each with semicolons so counts match."
        )

    results = []
    for msg, t in zip(messages, times):
        results.append(_create_single_reminder(msg, t))

    webhook_status = "Discord" if (DISCORD_WEBHOOK_URL and not DISCORD_WEBHOOK_URL.startswith("https://discord.com/api/webhooks/your")) else "local only (no webhook)"
    return f"Notify via {webhook_status}:\n" + "\n".join(results)


@tool
def reminder_list(show_delivered: bool = False) -> str:
    """List all upcoming reminders.

    Args:
        show_delivered: Whether to include already-delivered reminders.
    """
    path = _get_reminders_path()
    content = path.read_text()
    reminders = _parse_reminders(content)

    if not reminders:
        return "No reminders set. Use reminder_set to create one."

    pending = [r for r in reminders if not r["done"]]
    delivered = [r for r in reminders if r["done"]]

    lines = []
    if pending:
        lines.append(f"⏰ Upcoming ({len(pending)}):")
        for r in pending:
            lines.append(f"  - [ ] {r['datetime_str']} | {r['message']}")
    else:
        lines.append("No pending reminders.")

    if show_delivered and delivered:
        lines.append(f"\n✅ Delivered ({len(delivered)}):")
        for r in delivered:
            lines.append(f"  - [x] {r['datetime_str']} | {r['message']}")

    return "\n".join(lines)


@tool
def reminder_cancel(message_text: str) -> str:
    """Cancel a pending reminder by matching its message text.

    Args:
        message_text: Partial or full text of the reminder to cancel.
    """
    path = _get_reminders_path()
    content = path.read_text()
    lines = content.splitlines()

    for reminder in _parse_reminders(content):
        if reminder["done"]:
            continue
        if message_text.lower() in reminder["message"].lower():
            lines.pop(reminder["index"])
            path.write_text("\n".join(lines) + "\n")
            return f"Cancelled reminder: {reminder['datetime_str']} | {reminder['message']}"

    return f"No pending reminder matching '{message_text}' found."


# ── Work tools ───────────────────────────────────────────────────────


@tool
def work_log(entry: str) -> str:
    """Add an entry to today's work log. Auto-timestamps each entry.

    Good for tracking what you did, decisions made, issues hit, etc.
    Entries are stored in /work/YYYY-MM-DD.md.

    Args:
        entry: What you did, learned, or decided.
    """
    _ensure_vault()
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    day_name = now.strftime("%A")
    path = VAULT / f"work/{date_str}.md"

    if not path.exists():
        header = f"# Work Log — {date_str} ({day_name})\n\n"
        path.write_text(header)

    with open(path, "a") as f:
        f.write(f"- **{time_str}** — {entry}\n")

    return f"Logged at {time_str}: {entry}"


@tool
def work_standup(yesterday: str, today: str, blockers: str = "") -> str:
    """Write a daily standup entry. Stored in today's work log.

    Args:
        yesterday: What you accomplished yesterday.
        today: What you plan to do today.
        blockers: Any blockers or issues (optional).
    """
    _ensure_vault()
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    day_name = now.strftime("%A")
    path = VAULT / f"work/{date_str}.md"

    if not path.exists():
        header = f"# Work Log — {date_str} ({day_name})\n\n"
        path.write_text(header)

    standup = f"\n## Standup — {now.strftime('%H:%M')}\n\n"
    standup += f"**Yesterday:** {yesterday}\n\n"
    standup += f"**Today:** {today}\n\n"
    if blockers:
        standup += f"**Blockers:** {blockers}\n\n"

    with open(path, "a") as f:
        f.write(standup)

    return f"Standup logged for {date_str}"


@tool
def meeting_notes(title: str, attendees: str = "", notes: str = "", action_items: str = "") -> str:
    """Create a meeting notes file from a template.

    Args:
        title: Meeting title, e.g. 'Sprint Planning' or '1:1 with Manager'
        attendees: Comma-separated list of attendees (optional).
        notes: Meeting notes/discussion points (optional, can be added later).
        action_items: Action items from the meeting (optional).
    """
    _ensure_vault()
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    slug = re.sub(r'[^\w\s-]', '', title.lower()).replace(' ', '-')[:40]
    filename = f"meetings/{date_str}-{slug}.md"
    path = VAULT / filename

    content = f"# {title}\n\n"
    content += f"**Date:** {date_str} {time_str}\n"
    if attendees:
        content += f"**Attendees:** {attendees}\n"
    content += f"**Tags:** #meeting\n\n"
    content += "## Notes\n\n"
    if notes:
        content += f"{notes}\n\n"
    else:
        content += "_Add notes here_\n\n"
    content += "## Action Items\n\n"
    if action_items:
        for item in action_items.split(";"):
            item = item.strip()
            if item:
                content += f"- [ ] {item}\n"
    else:
        content += "- [ ] _Add action items_\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return f"Created meeting notes: /{filename}"


@tool
def quick_capture(text: str) -> str:
    """Quickly capture a thought, idea, or note. Auto-appended to today's daily note.

    Use this when the user wants to jot something down quickly without
    specifying where it should go.

    Args:
        text: The note, thought, or idea to capture.
    """
    _ensure_vault()
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    day_name = now.strftime("%A")
    path = VAULT / f"daily/{date_str}.md"

    if not path.exists():
        header = f"# Daily Note — {date_str} ({day_name})\n\n"
        path.write_text(header)

    with open(path, "a") as f:
        f.write(f"- {time_str} — {text}\n")

    return f"Captured to daily/{date_str}.md"


@tool
def weekly_summary() -> str:
    """Generate a summary of this week's work logs and daily notes.

    Reads all work logs and daily notes from the past 7 days and
    compiles them into a summary. Useful for weekly reviews and reports.
    """
    _ensure_vault()
    now = datetime.now()
    entries = []

    for days_ago in range(7):
        date = now - timedelta(days=days_ago)
        date_str = date.strftime("%Y-%m-%d")
        day_name = date.strftime("%A")

        work_path = VAULT / f"work/{date_str}.md"
        daily_path = VAULT / f"daily/{date_str}.md"

        day_content = []
        if work_path.exists():
            day_content.append(f"**Work Log:**\n{work_path.read_text()}")
        if daily_path.exists():
            day_content.append(f"**Daily Note:**\n{daily_path.read_text()}")

        if day_content:
            entries.append(f"### {date_str} ({day_name})\n\n" + "\n\n".join(day_content))

    if not entries:
        return "No work logs or daily notes found for the past 7 days."

    return f"# Weekly Summary ({(now - timedelta(days=6)).strftime('%m/%d')} – {now.strftime('%m/%d')})\n\n" + "\n\n---\n\n".join(entries)


# ── Escalation ───────────────────────────────────────────────────────


@tool
def ask_sonnet(question: str, context: str = "") -> str:
    """Escalate to Claude Sonnet for complex reasoning, planning, or analysis.

    Use this for tasks that need stronger analysis, summarization,
    project planning, or when you need deeper reasoning.

    Args:
        question: The question or task for Sonnet.
        context: Optional context to include (e.g. note contents).
    """
    from langchain_anthropic import ChatAnthropic
    from core.config import ANTHROPIC_API_KEY

    if not ANTHROPIC_API_KEY:
        return "Claude Sonnet is not configured. Set ANTHROPIC_API_KEY."

    try:
        llm = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=ANTHROPIC_API_KEY,
            temperature=0.0,
        )
        prompt = question
        if context:
            prompt = f"Context:\n{context}\n\nQuestion: {question}"
        response = llm.invoke(prompt)
        return f"[Sonnet] {response.content}"
    except Exception as e:
        return f"Sonnet escalation failed: {str(e)}"


# ── Tool registry ────────────────────────────────────────────────────

ALL_TOOLS = [
    # Vault CRUD
    vault_view,
    vault_create,
    vault_edit,
    vault_append,
    vault_delete,
    vault_search,
    # Tasks
    task_add,
    task_list,
    task_complete,
    task_remove,
    # Reminders
    reminder_set,
    reminder_list,
    reminder_cancel,
    # Work
    work_log,
    work_standup,
    meeting_notes,
    quick_capture,
    weekly_summary,
    # Escalation
    ask_sonnet,
]
