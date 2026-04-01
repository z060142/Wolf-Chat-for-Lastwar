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
                "You are archiving a completed conversation session for a chatbot. "
                "The bot operates inside a game chat environment and maintains a persona. "
                "The log contains exchanges between the bot and multiple different users.\n\n"
                "## Input format\n"
                "Each entry is prefixed with a username, e.g. '[timestamp] User (Alice): ...' "
                "and '[timestamp] Bot Dialogue: ...'. "
                "Bot Thoughts lines show internal reasoning and are included for context.\n\n"
                "## Output requirements\n"
                "Write a session summary covering:\n"
                "1. Which users participated and a one-line description of each.\n"
                "2. The overall tone and dynamic of the session.\n"
                "3. Anything significant that happened — notable requests, recurring topics, "
                "unusual behaviour, or events worth remembering in future sessions. "
                "Skip routine greetings and unremarkable small talk.\n\n"
                "## Constraints\n"
                "- Maximum 1500 characters.\n"
                "- Plain prose only. No bullet points, no headers, no preamble.\n"
                "- Write from the bot's perspective as the observer.\n"
                "- Write in English only. You may quote specific phrases from the log verbatim "
                "if they are distinctive or worth preserving, but all surrounding text must be English."
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
                "You are a character analyst writing a portrait of a person "
                "based on their observed behaviour in chat. "
                "Your output will be read by the bot before a live conversation "
                "so it knows who it is talking to — not what happened, but who this person is.\n\n"
                "Treat all conversation data as raw material. "
                "Do not narrate or summarise individual exchanges. "
                "Instead, draw conclusions about the person as a whole: "
                "their personality, their patterns, their tendencies.\n\n"
                "## Structure\n"
                "Write exactly four sections with these headings:\n\n"
                "**Interaction Style**\n"
                "How does this person communicate? Describe their characteristic tone, "
                "language habits, and the way they engage — as a stable pattern, "
                "not as a reaction to specific events. "
                "Write strictly from the bot's point of view as the one receiving this person. "
                "Do not mention what the bot says or does in response.\n\n"
                "**What They Come Here For**\n"
                "What does this person seem to want from these interactions? "
                "What do they talk about, initiate, or keep returning to? "
                "Write as a synthesis — a characterisation of their interests and intent, "
                "not a list of topics.\n\n"
                "**People & Relationships**\n"
                "Only record actual game players — identified by their in-game usernames. "
                "The qualifying condition is observed interaction: "
                "this user and the other person must have visibly engaged with each other in the log. "
                "A mere mention ('your dad', 'someone', 'a friend') does not qualify. "
                "Hypothetical references, third-party gossip, and unnamed figures must be excluded. "
                "For each person recorded, write one line describing the nature of the interaction.\n\n"
                "**Anchor Memories**\n"
                "Two or three moments that are genuinely distinctive or significant, "
                "each with a timestamp. These should reveal something about the person "
                "that the other sections cannot capture. "
                "Routine exchanges do not qualify. "
                "Prefer existing anchor memories unless a new moment is clearly more revealing."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Write a character portrait of '{username}' based on the following.\n\n"
                f"The conversation log is a shared window containing multiple users. "
                f"First identify all entries where '{username}' is speaking or directly involved, "
                f"then use only those as your source material.\n\n"
                f"Existing profile (carry forward what still holds true, revise what has changed):\n"
                f"{existing}\n\n"
                f"Conversation log (multiple users):\n{window_text}\n\n"
                f"Output at most 2500 characters. "
                f"Plain prose only. English only, except when quoting the user's own words verbatim."
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
                f"You are producing a compact memory note for the user '{username}' "
                "to be injected as live context at the start of a conversation.\n\n"
                "## Input format\n"
                "The conversation log is a shared window containing exchanges between "
                "the bot and multiple different users, interleaved chronologically. "
                "Each entry is prefixed with a username, e.g. '[timestamp] User (Alice): ...' "
                "and '[timestamp] Bot Dialogue: ...'. "
                f"First, extract only the entries where '{username}' is the speaker "
                "or is directly involved. Ignore all other users.\n\n"
                "## Output requirements\n"
                "Write 3 to 5 sentences covering:\n"
                "1. Who this person is — their communication style and personality as the bot experiences it.\n"
                "2. What they have been doing or discussing in recent interactions.\n"
                "3. The current tone of the relationship — how they tend to engage with the bot.\n\n"
                "## Constraints\n"
                "- Maximum 500 characters.\n"
                "- Plain prose only. No bullet points, no headers, no preamble.\n"
                "- Write in English only. You may quote specific phrases from the log verbatim "
                "if they are distinctive or worth preserving, but all surrounding text must be English.\n"
                "- If this user has no entries in the log, output exactly: (no recent activity)"
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
    import sys
    if not timestamp:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # Build window entry
    lines = [f"[{timestamp}] User ({username}): {user_input}"]
    if bot_thoughts:
        lines.append(f"[{timestamp}] Bot Thoughts: {bot_thoughts}")
    lines.append(f"[{timestamp}] Bot Dialogue: {bot_output}")
    entry = "\n".join(lines)

    print(f"[WolfMemory] record_interaction: username={username}, entry_len={len(entry)}",
          file=sys.stderr, flush=True)

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
