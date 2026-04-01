"""
Subprocess mode: JSON dispatcher over stdin/stdout.

Wolf-chat communicates by writing a JSON line to stdin.
Wolf-memory responds with a JSON line to stdout.

Each message is a single newline-terminated JSON object.
"""

import json
import sys

from . import core


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------

def _handle_query_user(params: dict) -> dict:
    username = params.get("username", "").strip()
    if not username:
        return _error("username is required")
    return core.query_user(username)


def _handle_record_interaction(params: dict) -> dict:
    username = params.get("username", "").strip()
    user_input = params.get("user_input", "")
    bot_thoughts = params.get("bot_thoughts", "")
    bot_output = params.get("bot_output", "")
    timestamp = params.get("timestamp")

    if not username:
        return _error("username is required")
    if not user_input and not bot_output:
        return _error("user_input or bot_output is required")

    core.record_interaction(
        username=username,
        user_input=user_input,
        bot_thoughts=bot_thoughts,
        bot_output=bot_output,
        timestamp=timestamp,
    )
    return {}


HANDLERS = {
    "query_user": _handle_query_user,
    "record_interaction": _handle_record_interaction,
    # Reserved (not yet implemented):
    # "query": _handle_query,
    # "search": _handle_search,
    # "list": _handle_list,
    # "read": _handle_read,
    # "write": _handle_write,
    # "update": _handle_update,
    # "consolidate": _handle_consolidate,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(data: dict) -> dict:
    return {"status": "ok", "data": data}


def _error(msg: str) -> dict:
    return {"status": "error", "error": msg, "data": {}}


def _respond(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run() -> None:
    """Read JSON requests from stdin line by line and respond to stdout."""
    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        try:
            request = json.loads(raw_line)
        except json.JSONDecodeError as e:
            _respond(_error(f"Invalid JSON: {e}"))
            continue

        action = request.get("action", "")
        params = request.get("params", {})

        handler = HANDLERS.get(action)
        if not handler:
            _respond(_error(f"Unknown action: {action}"))
            continue

        try:
            data = handler(params)
            if data.get("status") == "error":
                _respond(data)
            else:
                _respond(_ok(data))
        except Exception as e:
            _respond(_error(str(e)))
