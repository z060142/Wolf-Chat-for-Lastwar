"""
subprocess_api.py - JSON dispatcher over stdin/stdout.

Communication protocol:
  Request  (one JSON line on stdin):  { "action": "...", "params": { ... } }
  Response (one JSON line on stdout): { "status": "ok"|"error", "data": { ... }, "error": "..." }

The process runs in a loop, reading one request at a time, until EOF on stdin
(parent process closed the pipe) or a shutdown action is received.
"""

from __future__ import annotations

import json
import sys
from typing import Any


def _respond(status: str, data: Any = None, error: str = "") -> None:
    payload: dict[str, Any] = {"status": status, "data": data or {}}
    if error:
        payload["error"] = error
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def _dispatch(action: str, params: dict) -> None:
    from .core import query_user, record_interaction, query
    from .storage import ensure_layer_dirs

    # Ensure memory directories exist on first use
    ensure_layer_dirs()

    if action == "query_user":
        username = params.get("username", "").strip()
        if not username:
            _respond("error", error="Missing required param: username")
            return
        data = query_user(username)
        _respond("ok", data)

    elif action == "record_interaction":
        required = ["username", "timestamp", "user_input", "bot_thoughts", "bot_output"]
        missing = [k for k in required if not params.get(k)]
        if missing:
            _respond("error", error=f"Missing required params: {', '.join(missing)}")
            return
        result = record_interaction(
            username=params["username"],
            timestamp=params["timestamp"],
            user_input=params["user_input"],
            bot_thoughts=params["bot_thoughts"],
            bot_output=params["bot_output"],
        )
        if result.get("status") == "error":
            _respond("error", error=result.get("error", "Unknown error"))
        else:
            _respond("ok")

    elif action == "query":
        input_text = params.get("input", "").strip()
        if not input_text:
            _respond("error", error="Missing required param: input")
            return
        username = params.get("username")
        data = query(input_text, username=username)
        _respond("ok", data)

    else:
        _respond("error", error=f"Unknown action: {action!r}")


def run_subprocess_loop() -> None:
    """
    Main loop: read JSON lines from stdin, dispatch, write JSON to stdout.
    Exits cleanly on EOF or when the parent closes stdin.
    """
    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        try:
            request = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            _respond("error", error=f"Invalid JSON: {exc}")
            continue

        action = request.get("action", "")
        params = request.get("params", {})

        if action == "shutdown":
            _respond("ok", {"message": "shutting down"})
            break

        try:
            _dispatch(action, params)
        except Exception as exc:
            _respond("error", error=f"Internal error: {exc}")
