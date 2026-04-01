"""
Wolf Memory - unified entry point.

Usage:
  python main.py --mode subprocess   # default, for wolf-chat integration
  python main.py --mode cli          # interactive CLI (not yet implemented)
  python main.py --mode mcp          # MCP server (not yet implemented)
"""

import argparse
import threading
import time


def _start_hourly_scheduler() -> None:
    """Background thread: trigger compact refresh every hour."""
    from wolf_memory import core

    def _loop():
        while True:
            time.sleep(3600)
            try:
                core.run_hourly_compact()
            except Exception as e:
                print(f"[wolf-memory] hourly compact error: {e}", flush=True)

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
        _start_hourly_scheduler()
        from wolf_memory.subprocess_api import run
        run()

    elif args.mode == "cli":
        print("[wolf-memory] CLI mode not yet implemented.")

    elif args.mode == "mcp":
        print("[wolf-memory] MCP mode not yet implemented.")


if __name__ == "__main__":
    main()
