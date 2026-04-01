"""
wolf_memory_bridge.py

Shared WolfMemoryClient class used by both main.py and test/llm_debug_script.py.
Manages the wolf-memory subprocess and communicates via JSON over stdin/stdout.
"""

import json
import logging
import os
import subprocess
import sys
import threading

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class WolfMemoryClient:
    """
    Manages the wolf-memory subprocess and communicates via JSON over stdin/stdout.
    Fails silently so that wolf-chat continues operating even if wolf-memory is unavailable.
    """

    def __init__(self):
        self._proc = None
        self._lock = threading.Lock()

    def start(self, backend: str = "", host: str = "", model: str = "", data_dir: str = ""):
        """
        Start the wolf-memory subprocess.
        data_dir: override the memories directory (useful for test mode).
        """
        memory_script = os.path.join(_BASE_DIR, "wolf-memory", "main.py")
        if not os.path.exists(memory_script):
            logger.warning("[WolfMemory] wolf-memory/main.py not found, memory system disabled.")
            print("[WolfMemory] wolf-memory/main.py not found, memory system disabled.")
            return

        env = os.environ.copy()
        # Force UTF-8 I/O in the subprocess so JSON pipe communication works on
        # Windows systems with non-UTF-8 default encodings (e.g. CP950 / Big5).
        env["PYTHONIOENCODING"] = "utf-8"
        if backend:
            env["WOLF_MEMORY_BACKEND"] = backend
        if host:
            env["OLLAMA_HOST"] = host
        if model:
            env["WOLF_MEMORY_MODEL"] = model
        if data_dir:
            env["WOLF_MEMORY_DATA_DIR"] = data_dir

        try:
            self._proc = subprocess.Popen(
                [sys.executable, memory_script, "--mode", "subprocess"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                env=env,
            )
            # Give the subprocess a moment to start, then check if it crashed
            import time
            time.sleep(0.3)
            if self._proc.poll() is not None:
                stderr_output = self._proc.stderr.read()
                logger.error(f"[WolfMemory] Subprocess exited immediately.\n{stderr_output}")
                print(f"[WolfMemory] Subprocess exited immediately. stderr:\n{stderr_output}")
                self._proc = None
                return

            # Start a daemon thread to forward subprocess stderr to console
            def _stderr_forwarder():
                for line in self._proc.stderr:
                    print(f"[WolfMemory stderr] {line}", end="", flush=True)
            t = threading.Thread(target=_stderr_forwarder, daemon=True)
            t.start()

            logger.info("[WolfMemory] Subprocess started.")
            print("[WolfMemory] Subprocess started.")
        except Exception as e:
            logger.error(f"[WolfMemory] Failed to start subprocess: {e}")
            print(f"[WolfMemory] Failed to start subprocess: {e}")
            self._proc = None

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _send(self, action: str, params: dict) -> dict | None:
        if not self.is_running():
            logger.warning(f"[WolfMemory] Subprocess not running, dropping action: {action}")
            print(f"[WolfMemory] WARNING: Subprocess not running, dropping action: {action}")
            return None
        with self._lock:
            try:
                line = json.dumps({"action": action, "params": params}, ensure_ascii=False) + "\n"
                self._proc.stdin.write(line)
                self._proc.stdin.flush()
                response_line = self._proc.stdout.readline()
                if response_line:
                    return json.loads(response_line)
                logger.error(f"[WolfMemory] Empty response from subprocess for action: {action}")
                print(f"[WolfMemory] ERROR: Empty response from subprocess for action: {action}")
            except Exception as e:
                logger.error(f"[WolfMemory] Communication error ({action}): {e}")
                print(f"[WolfMemory] ERROR: Communication error ({action}): {e}")
        return None

    def query_user(self, username: str) -> dict | None:
        """Query memory for a user. Returns data dict or None on failure."""
        result = self._send("query_user", {"username": username})
        if result and result.get("status") == "ok":
            return result.get("data")
        if result and result.get("status") == "error":
            logger.error(f"[WolfMemory] query_user error: {result.get('error')}")
            print(f"[WolfMemory] ERROR: query_user: {result.get('error')}")
        return None

    def record_interaction(self, username: str, user_input: str,
                           bot_thoughts: str, bot_output: str,
                           timestamp: str | None = None) -> None:
        """Record a conversation interaction."""
        params = {
            "username": username,
            "user_input": user_input,
            "bot_thoughts": bot_thoughts,
            "bot_output": bot_output,
        }
        if timestamp:
            params["timestamp"] = timestamp
        result = self._send("record_interaction", params)
        if result and result.get("status") == "error":
            logger.error(f"[WolfMemory] record_interaction error: {result.get('error')}")
            print(f"[WolfMemory] ERROR: record_interaction: {result.get('error')}")

    def terminate(self):
        """Terminate the wolf-memory subprocess."""
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdin.close()
                self._proc.terminate()
                self._proc.wait(timeout=5)
                logger.info("[WolfMemory] Subprocess terminated.")
                print("[WolfMemory] Subprocess terminated.")
            except Exception as e:
                logger.warning(f"[WolfMemory] Error terminating subprocess: {e}")
                try:
                    self._proc.kill()
                except Exception:
                    pass
