"""
Wolf Memory - unified entry point.

Usage:
  python main.py --mode subprocess   # default, for wolf-chat integration
  python main.py --mode cli          # interactive CLI (not yet implemented)
  python main.py --mode mcp          # MCP server (not yet implemented)

IMPORTANT: In subprocess mode, stdout is reserved for JSON communication.
All diagnostic output must go to stderr.
"""

import argparse
import sys
import threading
import time

# Force UTF-8 on stdout/stderr so JSON communication works regardless of OS locale.
# On Windows with Traditional Chinese locale (CP950), the default encoding would break
# JSON encoding of non-ASCII characters when the parent reads the pipe as UTF-8.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def _log(msg: str) -> None:
    """Write diagnostic message to stderr (stdout is reserved for JSON in subprocess mode)."""
    print(msg, file=sys.stderr, flush=True)


def _start_hourly_scheduler() -> None:
    """Background thread: trigger compact refresh every hour."""
    from wolf_memory import core

    def _loop():
        while True:
            time.sleep(3600)
            try:
                core.run_hourly_compact()
            except Exception as e:
                _log(f"[wolf-memory] hourly compact error: {e}")

    t = threading.Thread(target=_loop, daemon=True)
    t.start()


def main() -> None:
    parser = argparse.ArgumentParser(description="Wolf Memory")
    parser.add_argument(
        "--mode",
        choices=["subprocess", "cli", "mcp"],
        default="subprocess",
        help="Execution mode (default: subprocess)",
    )
    args = parser.parse_args()

    if args.mode == "subprocess":
        from wolf_memory import index_manager
        index_manager.reconcile_on_startup()
        _start_hourly_scheduler()
        from wolf_memory.subprocess_api import run
        run()

    elif args.mode == "cli":
        print("[wolf-memory] CLI mode not yet implemented.")

    elif args.mode == "mcp":
        print("[wolf-memory] MCP mode not yet implemented.")


if __name__ == "__main__":
    main()
