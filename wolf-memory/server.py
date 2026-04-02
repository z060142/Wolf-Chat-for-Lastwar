"""
server.py - Wolf Memory unified entry point.

Usage:
    python server.py --mode subprocess   # stdin/stdout JSON loop (wolf-chat integration)
    python server.py --mode cli          # interactive CLI (reserved)
    python server.py --mode mcp          # MCP server (reserved)

Default mode is subprocess.
"""

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Wolf Memory server")
    parser.add_argument(
        "--mode",
        choices=["subprocess", "cli", "mcp"],
        default="subprocess",
        help="Execution mode (default: subprocess)",
    )
    args = parser.parse_args()

    if args.mode == "subprocess":
        from wolf_memory.subprocess_api import run_subprocess_loop
        run_subprocess_loop()

    elif args.mode == "cli":
        print("CLI mode is not yet implemented.", file=sys.stderr)
        sys.exit(1)

    elif args.mode == "mcp":
        print("MCP server mode is not yet implemented.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
