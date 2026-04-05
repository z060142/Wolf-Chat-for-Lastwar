"""Wolfina-Wiki entry point.

Usage:
    uv run python wiki_app.py                  # Standalone: GUI + API server
    uv run python wiki_app.py --no-gui         # Headless API server only
    uv run python wiki_app.py --mode subprocess  # stdin/stdout IPC mode (for wolf-chat)

The API server always starts on the configured port (default 8765).
The GUI runs in the main thread when enabled.
The API server runs in a background daemon thread.
"""

import argparse
import json
import logging
import sys
import threading
import time

import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("wiki_app")


def start_api_server(port: int) -> None:
    """Start uvicorn in a daemon thread."""
    from api.app import app

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        loop="asyncio",
    )
    server = uvicorn.Server(config)

    def _run() -> None:
        import asyncio
        asyncio.run(server.serve())

    thread = threading.Thread(target=_run, daemon=True, name="uvicorn")
    thread.start()
    logger.info(f"API server starting on http://127.0.0.1:{port}")
    # Give uvicorn a moment to bind
    time.sleep(1.5)


def subprocess_loop() -> None:
    """Read newline-delimited JSON from stdin, forward to conversation buffer.

    Each line: {"speaker": "...", "content": "...", "timestamp": "..."}
    Sends status lines to stdout: {"status": "ok", "message_id": "..."}
    """
    from core.conversation_buffer import conversation_buffer

    logger.info("Subprocess mode active — reading from stdin.")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            msg = conversation_buffer.add_message(
                speaker=data.get("speaker", "unknown"),
                content=data.get("content", ""),
            )
            response = {"status": "ok", "message_id": msg.id}
        except Exception as e:
            response = {"status": "error", "detail": str(e)}
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="Wolfina Wiki")
    parser.add_argument("--no-gui", action="store_true", help="Run headless (no Tkinter window)")
    parser.add_argument(
        "--mode", choices=["standalone", "subprocess"], default="standalone",
        help="standalone: normal operation; subprocess: IPC via stdin/stdout",
    )
    args = parser.parse_args()

    from core.settings import settings

    # Always start the API server
    start_api_server(settings.api_port)

    if args.mode == "subprocess":
        # Subprocess mode: read messages from stdin, no GUI
        try:
            subprocess_loop()
        except KeyboardInterrupt:
            pass
        return

    if args.no_gui:
        logger.info("Headless mode — API server running. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        return

    # Default: launch GUI (blocks until window is closed)
    try:
        from gui.main_window import launch_gui
        launch_gui()
    except ImportError as e:
        logger.error(f"Could not import GUI (tkinter missing?): {e}")
        logger.info("Falling back to headless mode.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
