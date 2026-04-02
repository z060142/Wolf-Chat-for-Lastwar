"""
core.py - High-level API: query_user, record_interaction, query (semantic).

This module is the main logic layer. It sits above storage / index / tools
and is called by subprocess_api.py (and eventually mcp_server.py / cli.py).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .index_manager import entity_exists, get_entity_files, register_file
from .settings import LLM_BACKEND, MEMORIES_DIR, OLLAMA_API_KEY, OLLAMA_HOST, OLLAMA_MODEL
from .storage import new_working_file, read_file
from .stream_parser import run_llm_with_tools
from .tools import TOOL_SCHEMAS


# ---------------------------------------------------------------------------
# query_user
# ---------------------------------------------------------------------------

def query_user(username: str) -> dict[str, Any]:
    """
    Retrieve structured memory data for a user before starting a conversation.

    Returns:
        {
            "username": str,
            "found": bool,
            "profile": { "tags": [...], "summary": "..." },   # only if found
            "recent_interactions": [ {...}, ... ]              # only if found
        }
    """
    if not entity_exists(username):
        # Auto-create empty placeholder so we know the user exists going forward
        _ensure_entity_placeholder(username)
        return {"username": username, "found": False}

    entry = get_entity_files(username) or {}

    # Build profile from core file (if exists)
    profile: dict[str, Any] = {"tags": entry.get("tags", []), "summary": ""}
    core_path = entry.get("core")
    if core_path:
        try:
            meta, body = read_file(core_path)
            profile["summary"] = meta.get("summary", body[:300].strip())
            profile["tags"] = meta.get("tags") or profile["tags"]
        except Exception:
            pass

    # Collect recent working-layer interactions (up to 10, newest first)
    working_files: list[str] = list(reversed(entry.get("working", [])))[:10]
    recent: list[dict] = []
    for wf in working_files:
        try:
            meta, body = read_file(wf)
            recent.append({
                "timestamp": meta.get("created_at", ""),
                "raw": body.strip(),
            })
        except Exception:
            continue

    return {
        "username": username,
        "found": True,
        "profile": profile,
        "recent_interactions": recent,
    }


def _ensure_entity_placeholder(username: str) -> None:
    """Register the username in the index without creating any file."""
    from .index_manager import load_index, save_index, _ensure_entity
    index = load_index()
    _ensure_entity(index, username)
    save_index(index)


# ---------------------------------------------------------------------------
# record_interaction
# ---------------------------------------------------------------------------

def record_interaction(
    username: str,
    timestamp: str,
    user_input: str,
    bot_thoughts: str,
    bot_output: str,
) -> dict[str, Any]:
    """
    Persist a single interaction to the working layer and update the index.

    Called synchronously after wolf-chat finishes generating a response.
    Returns {"status": "ok"} or {"status": "error", "error": "..."}.
    """
    try:
        rel_path = new_working_file(
            username=username,
            timestamp=timestamp,
            user_input=user_input,
            bot_thoughts=bot_thoughts,
            bot_output=bot_output,
        )
        register_file(str(rel_path), username, "working")
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# query (semantic, LLM-driven)
# ---------------------------------------------------------------------------

def query(input_text: str, username: str | None = None) -> dict[str, Any]:
    """
    Answer a natural-language question by driving the LLM to read memory files
    via tool calls.

    Args:
        input_text: The question, in any language.
        username:   Optional. If given, the LLM is hinted to focus on this user.

    Returns:
        {
            "answer": str,
            "sources": [list of file paths the LLM read]
        }
    """
    scope_hint = (
        f"Focus on files related to entity '{username}'." if username else "Search globally."
    )

    system_prompt = (
        "You are a memory retrieval assistant. "
        "Use the available tools to read memory files and answer the user's question. "
        "After gathering enough information, write your final answer. "
        "Respond in the same language as the user's question. "
        f"{scope_hint}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": input_text},
    ]

    result = run_llm_with_tools(
        messages=messages,
        tools=TOOL_SCHEMAS,
        backend=LLM_BACKEND,
        model=OLLAMA_MODEL,
        ollama_host=OLLAMA_HOST,
        ollama_api_key=OLLAMA_API_KEY,
    )

    sources = [
        tc["args"].get("file_path", "")
        for tc in result.tool_calls_executed
        if tc["name"] == "read_file"
    ]

    return {
        "answer": result.text.strip(),
        "sources": [s for s in sources if s],
    }
