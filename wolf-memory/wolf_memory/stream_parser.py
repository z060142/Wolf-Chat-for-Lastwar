"""
Streaming LLM output parser with real-time tool call interception.

Supports both Ollama SDK and requests (raw HTTP) backends.
When a tool_call is detected mid-stream, the tool is executed immediately
without waiting for the stream to finish.
"""

import json
from collections.abc import Generator, Iterator
from typing import Any

from .tools import dispatch


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class TextChunk:
    def __init__(self, text: str):
        self.text = text


class ToolCall:
    def __init__(self, name: str, args: dict, result: dict):
        self.name = name
        self.args = args
        self.result = result


class StreamDone:
    pass


# ---------------------------------------------------------------------------
# Ollama SDK stream parser
# ---------------------------------------------------------------------------

def parse_ollama_stream(
    stream: Iterator,
) -> Generator[TextChunk | ToolCall | StreamDone, None, None]:
    """
    Parse an Ollama SDK streaming response.
    Executes tool calls immediately when encountered.
    """
    for chunk in stream:
        msg = chunk.get("message", {})

        # Text content
        content = msg.get("content", "")
        if content:
            yield TextChunk(content)

        # Tool calls (Ollama delivers these as complete objects in a single chunk)
        for tc in msg.get("tool_calls", []):
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            result = dispatch(name, args)
            yield ToolCall(name=name, args=args, result=result)

        if chunk.get("done"):
            yield StreamDone()
            return


# ---------------------------------------------------------------------------
# requests (HTTP) stream parser
# ---------------------------------------------------------------------------

def parse_requests_stream(
    response,
) -> Generator[TextChunk | ToolCall | StreamDone, None, None]:
    """
    Parse a raw HTTP streaming response from /api/chat (NDJSON lines).
    Executes tool calls immediately when encountered.
    """
    for raw_line in response.iter_lines():
        if not raw_line:
            continue
        try:
            chunk = json.loads(raw_line)
        except json.JSONDecodeError:
            continue

        msg = chunk.get("message", {})

        content = msg.get("content", "")
        if content:
            yield TextChunk(content)

        for tc in msg.get("tool_calls", []):
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            result = dispatch(name, args)
            yield ToolCall(name=name, args=args, result=result)

        if chunk.get("done"):
            yield StreamDone()
            return


# ---------------------------------------------------------------------------
# Collect full text from a stream (for non-interactive use)
# ---------------------------------------------------------------------------

def collect_text(
    stream: Generator[TextChunk | ToolCall | StreamDone, None, None],
) -> tuple[str, list[ToolCall]]:
    """
    Consume a parsed stream, return (full_text, tool_calls_executed).
    Tool calls are already executed as a side effect during iteration.
    """
    parts = []
    calls = []
    for event in stream:
        if isinstance(event, TextChunk):
            parts.append(event.text)
        elif isinstance(event, ToolCall):
            calls.append(event)
    return "".join(parts), calls
