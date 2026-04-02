"""
wolf_memory_client.py - Wolf Memory subprocess client for wolf-chat.

Manages the lifetime of the wolf-memory subprocess and provides
async-friendly query_user / record_interaction wrappers.

The subprocess communicates via JSON lines over stdin/stdout:
  Request:  { "action": "...", "params": { ... } }
  Response: { "status": "ok"|"error", "data": { ... }, "error": "..." }

Design goals:
  - Non-blocking: all I/O delegated to a thread executor
  - Fault-tolerant: failures are logged but never crash wolf-chat
  - Single subprocess kept alive for the session lifetime
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Path to wolf-memory server.py, relative to this file
_SERVER_SCRIPT = Path(__file__).parent / "wolf-memory" / "server.py"


class WolfMemoryClient:
    """Long-lived subprocess client for wolf-memory."""

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._enabled = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """
        Launch the wolf-memory subprocess.
        Returns True if started successfully, False otherwise.
        """
        if not _SERVER_SCRIPT.exists():
            logger.warning(f"[WolfMemory] server.py not found at {_SERVER_SCRIPT}, skipping.")
            return False

        try:
            self._process = subprocess.Popen(
                [sys.executable, str(_SERVER_SCRIPT), "--mode", "subprocess"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,  # line-buffered
            )
            self._enabled = True
            logger.info(f"[WolfMemory] Subprocess started (PID {self._process.pid})")
            return True
        except Exception as exc:
            logger.error(f"[WolfMemory] Failed to start subprocess: {exc}")
            return False

    def stop(self) -> None:
        """Gracefully shut down the subprocess."""
        if not self._process:
            return
        try:
            with self._lock:
                self._send_raw({"action": "shutdown", "params": {}})
            self._process.wait(timeout=5)
        except Exception:
            pass
        finally:
            try:
                self._process.terminate()
            except Exception:
                pass
            self._process = None
            self._enabled = False
            logger.info("[WolfMemory] Subprocess stopped.")

    # ------------------------------------------------------------------
    # Low-level I/O (called from thread executor — not async-safe directly)
    # ------------------------------------------------------------------

    def _send_raw(self, request: dict) -> dict:
        """
        Send one JSON request and read one JSON response.
        Must be called with self._lock held.
        Thread-safe, blocking.
        """
        if not self._process or self._process.stdin is None or self._process.stdout is None:
            return {"status": "error", "data": {}, "error": "Subprocess not running"}

        line = json.dumps(request, ensure_ascii=False) + "\n"
        self._process.stdin.write(line)
        self._process.stdin.flush()

        response_line = self._process.stdout.readline()
        if not response_line:
            return {"status": "error", "data": {}, "error": "Empty response from subprocess"}

        try:
            return json.loads(response_line.strip())
        except json.JSONDecodeError as exc:
            return {"status": "error", "data": {}, "error": f"Invalid JSON response: {exc}"}

    def _call_sync(self, action: str, params: dict) -> dict:
        """Thread-safe synchronous call. Returns the full response dict."""
        if not self._enabled:
            return {"status": "error", "data": {}, "error": "WolfMemory not enabled"}
        try:
            with self._lock:
                return self._send_raw({"action": action, "params": params})
        except Exception as exc:
            logger.error(f"[WolfMemory] Error calling {action}: {exc}")
            return {"status": "error", "data": {}, "error": str(exc)}

    # ------------------------------------------------------------------
    # Async public API (run sync I/O in thread executor)
    # ------------------------------------------------------------------

    async def query_user(self, username: str) -> dict[str, Any]:
        """
        Retrieve structured memory for a user before LLM processing.

        Returns dict with keys: username, found, profile, recent_interactions
        Returns empty dict on failure (wolf-chat continues normally).
        """
        if not self._enabled:
            return {}
        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None,
                self._call_sync,
                "query_user",
                {"username": username},
            )
            if response.get("status") == "ok":
                return response.get("data", {})
            else:
                logger.warning(f"[WolfMemory] query_user error: {response.get('error')}")
                return {}
        except Exception as exc:
            logger.error(f"[WolfMemory] query_user exception: {exc}")
            return {}

    async def record_interaction(
        self,
        username: str,
        timestamp: str,
        user_input: str,
        bot_thoughts: str,
        bot_output: str,
    ) -> None:
        """
        Persist an interaction to wolf-memory working layer.
        Runs in thread executor; errors are logged but never raised.
        """
        if not self._enabled:
            return
        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None,
                self._call_sync,
                "record_interaction",
                {
                    "username": username,
                    "timestamp": timestamp,
                    "user_input": user_input,
                    "bot_thoughts": bot_thoughts,
                    "bot_output": bot_output,
                },
            )
            if response.get("status") != "ok":
                logger.warning(f"[WolfMemory] record_interaction error: {response.get('error')}")
        except Exception as exc:
            logger.error(f"[WolfMemory] record_interaction exception: {exc}")


# Module-level singleton — imported and used by main.py
wolf_memory = WolfMemoryClient()
