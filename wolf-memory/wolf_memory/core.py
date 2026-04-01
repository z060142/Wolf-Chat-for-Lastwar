"""
Core logic: LLM client, background agents, and the main API operations.

Operations:
  - query_user(username)       → structured data for wolf-chat
  - record_interaction(...)    → append to window, trigger background jobs
  - _update_persona(username)  → background LLM job
  - _archive_window()          → background LLM job
  - _update_compact(username)  → background LLM job
  - run_hourly_compact()       → sweep all dirty users (called by scheduler)
"""

import json
import threading
from datetime import datetime, timezone
from queue import Queue

import requests as _requests

from . import index_manager, storage
from .config import (
    COMPACT_MIN_INTERVAL_HOURS,
    LLM_BACKEND,
    MAX_CONCURRENT_AGENTS,
    OLLAMA_API_KEY,
    OLLAMA_HOST,
    OLLAMA_MODEL,
    PERSONA_UPDATE_INTERVAL,
)
from .stream_parser import (
    collect_text,
    parse_ollama_stream,
    parse_requests_stream,
)
from .tools import TOOL_DEFINITIONS


# ---------------------------------------------------------------------------
# Agent queue (max 3 concurrent LLM agents)
# ---------------------------------------------------------------------------

_agent_semaphore = threading.Semaphore(MAX_CONCURRENT_AGENTS)
_bg_queue: Queue = Queue()


def _run_agent(fn, *args, **kwargs) -> None:
    """Run fn in a background thread, respecting the semaphore limit."""
    def _worker():
        _agent_semaphore.acquire()
        try:
            fn(*args, **kwargs)
        finally:
            _agent_semaphore.release()

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# LLM client (dual backend)
# ---------------------------------------------------------------------------

def _chat(messages: list[dict], tools: list | None = None) -> tuple[str, list]:
    """
    Send a chat request and return (full_text, tool_calls_executed).
    Handles both 'ollama' and 'requests' backends.
    Tool calls are executed in real-time during streaming.
    """
    if LLM_BACKEND == "ollama":
        return _chat_ollama(messages, tools)
    return _chat_requests(messages, tools)


def _chat_ollama(messages: list[dict], tools: list | None = None) -> tuple[str, list]:
    from ollama import Client

    kwargs = {"host": OLLAMA_HOST}
    if OLLAMA_API_KEY:
        kwargs["headers"] = {"Authorization": f"Bearer {OLLAMA_API_KEY}"}

    client = Client(**kwargs)
    call_kwargs: dict = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": True,
    }
    if tools:
        call_kwargs["tools"] = tools

    stream = client.chat(**call_kwargs)
    return collect_text(parse_ollama_stream(stream))


def _chat_requests(messages: list[dict], tools: list | None = None) -> tuple[str, list]:
    headers = {"Content-Type": "application/json"}
    if OLLAMA_API_KEY:
        headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"

    payload: dict = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": True,
    }
    if tools:
        payload["tools"] = tools

    response = _requests.post(
        f"{OLLAMA_HOST}/api/chat",
        headers=headers,
        json=payload,
        stream=True,
        timeout=120,
    )
    response.raise_for_status()
    return collect_text(parse_requests_stream(response))


# ---------------------------------------------------------------------------
# Background jobs
# ---------------------------------------------------------------------------

def _archive_window() -> None:
    """LLM summarises the current window and archives it."""
    window_text = storage.read_window()
    if not window_text.strip():
        return

    messages = [
        {
            "role": "system",
            "content": (
                "You are a memory archivist. "
                "Summarise the following chat log concisely. "
                "Include: who participated, what they did, and anything notable. "
                "Write in plain text, no bullet headers needed."
            ),
        },
        {"role": "user", "content": window_text},
    ]
    summary, _ = _chat(messages)

    seq = storage.next_archive_sequence()
    storage.save_archive(summary, seq)
    storage.reset_window(opening_summary=summary)
    index_manager.reset_window_count()


def _update_persona(username: str) -> None:
    """LLM updates persona.md for a user using the full window + existing persona."""
    window_text = storage.read_window()
    persona_post = storage.read_persona(username)
    existing = persona_post.content if persona_post else "(no existing data)"

    messages = [
        {
            "role": "system",
            "content": (
                f"You are updating a character profile for '{username}'. "
                "Read the full conversation log and the existing profile. "
                "Update the profile to reflect recent interactions. "
                "Emphasise recent behaviour; let old details fade if not reinforced. "
                "Include: (1) commentary on their interaction style, "
                "(2) recent activities, "
                "(3) people they interact with or mention and the relationship status, "
                "(4) notable events with timestamps (ignore position-removal requests). "
                "Write in plain text."
            ),
        },
        {
            "role": "user",
            "content": (
                f"## Existing profile\n{existing}\n\n"
                f"## Full conversation log\n{window_text}"
            ),
        },
    ]
    updated, _ = _chat(messages)
    storage.write_persona(username, updated)
    index_manager.mark_persona_updated(username)


def _update_compact(username: str) -> None:
    """LLM produces a compact summary of the window focused on a specific user."""
    window_text = storage.read_window()
    if not window_text.strip():
        return

    messages = [
        {
            "role": "system",
            "content": (
                f"You are summarising recent chat activity involving '{username}'. "
                "Read the conversation log and produce a brief summary (3-6 sentences) "
                "that answers: who is this person, what have they done recently, "
                "and what is their current relationship with the bot. "
                "This will be used as context during live conversations."
            ),
        },
        {"role": "user", "content": window_text},
    ]
    summary, _ = _chat(messages)
    storage.write_compact(username, summary)
    index_manager.mark_compact_updated(username)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def query_user(username: str) -> dict:
    """
    Return structured memory data for a user.
    Creates an empty record if the user is new.
    """
    is_new = not index_manager.user_exists(username)

    if is_new:
        index_manager.register_user(username)
        storage.create_empty_persona(username)
        return {"username": username, "found": False}

    persona_post = storage.read_persona(username)
    compact_post = storage.read_compact(username)

    # Trigger a background compact refresh if stale (non-blocking)
    if index_manager.compact_needs_refresh(username, COMPACT_MIN_INTERVAL_HOURS):
        _run_agent(_update_compact, username)

    persona_content = persona_post.content.strip() if persona_post else ""
    compact_content = compact_post.content.strip() if compact_post else ""

    if not persona_content and not compact_content:
        return {"username": username, "found": False}

    return {
        "username": username,
        "found": True,
        "persona": persona_content,
        "compact_summary": compact_content,
    }


def record_interaction(
    username: str,
    user_input: str,
    bot_thoughts: str,
    bot_output: str,
    timestamp: str | None = None,
) -> None:
    """
    Append a conversation entry to the shared window and trigger background jobs.
    """
    if not timestamp:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # Build window entry
    lines = [f"[{timestamp}] User ({username}): {user_input}"]
    if bot_thoughts:
        lines.append(f"[{timestamp}] Bot Thoughts: {bot_thoughts}")
    lines.append(f"[{timestamp}] Bot Dialogue: {bot_output}")
    entry = "\n".join(lines)

    # Append and get new count
    new_count = storage.append_to_window(entry)
    index_manager.increment_window_count()

    # Register user if new
    if not index_manager.user_exists(username):
        index_manager.register_user(username)
        storage.create_empty_persona(username)

    user_state = index_manager.record_conversation(username)

    # Trigger: archive window if full
    if new_count >= 50:
        _run_agent(_archive_window)

    # Trigger: persona update every N conversations
    if index_manager.should_update_persona(username, PERSONA_UPDATE_INTERVAL):
        _run_agent(_update_persona, username)


def run_hourly_compact() -> None:
    """
    Sweep all dirty users and schedule compact updates.
    Meant to be called by the hourly scheduler in main.py.
    """
    for username in index_manager.get_all_dirty_users():
        if index_manager.compact_needs_refresh(username, COMPACT_MIN_INTERVAL_HOURS):
            _run_agent(_update_compact, username)
