"""
stream_parser.py - Streaming response parser with real-time tool call interception.

Handles two LLM backends:
  - ollama package  (response is an iterator of Message objects)
  - requests        (response is a raw streaming HTTP response with JSON lines)

When a tool_call is detected mid-stream, it is executed immediately via tools.py
and the result is fed back to the LLM as a tool result message, without waiting
for the full stream to finish.
"""

from __future__ import annotations

import json
from typing import Any, Generator

from .tools import execute_tool


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

class StreamResult:
    """Accumulates LLM text output and tracks tool calls executed."""

    def __init__(self) -> None:
        self.text: str = ""
        self.tool_calls_executed: list[dict] = []

    def append_text(self, chunk: str) -> None:
        self.text += chunk

    def record_tool_call(self, name: str, args: dict, result: str) -> None:
        self.tool_calls_executed.append({"name": name, "args": args, "result": result})


# ---------------------------------------------------------------------------
# Ollama-package backend
# ---------------------------------------------------------------------------

def run_with_ollama_client(
    client: Any,
    model: str,
    messages: list[dict],
    tools: list[dict],
    max_tool_rounds: int = 10,
) -> StreamResult:
    """
    Drive a tool-use conversation loop using the `ollama` Python package.

    The ollama package handles the stream internally; we iterate over chunks
    and look for tool_calls in the finish delta.
    """
    result = StreamResult()
    history = list(messages)

    for _ in range(max_tool_rounds):
        response = client.chat(
            model=model,
            messages=history,
            tools=tools,
            stream=True,
        )

        accumulated_text = ""
        pending_tool_calls: list[dict] = []

        for chunk in response:
            msg = chunk.get("message", {}) if isinstance(chunk, dict) else getattr(chunk, "message", {})
            if isinstance(msg, dict):
                content = msg.get("content", "")
                tool_calls = msg.get("tool_calls") or []
            else:
                content = getattr(msg, "content", "") or ""
                tool_calls = getattr(msg, "tool_calls", None) or []

            if content:
                accumulated_text += content
                result.append_text(content)

            for tc in tool_calls:
                if isinstance(tc, dict):
                    fn = tc.get("function", {})
                    name = fn.get("name", "")
                    args = fn.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                else:
                    fn = getattr(tc, "function", None)
                    name = getattr(fn, "name", "") if fn else ""
                    args = getattr(fn, "arguments", {}) if fn else {}
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                pending_tool_calls.append({"name": name, "args": args})

        if not pending_tool_calls:
            # No tool calls — conversation complete
            break

        # Execute all tool calls and build follow-up messages
        if accumulated_text:
            history.append({"role": "assistant", "content": accumulated_text})

        for tc in pending_tool_calls:
            name = tc["name"]
            args = tc["args"]
            tool_result = execute_tool(name, args)
            result.record_tool_call(name, args, tool_result)
            history.append({
                "role": "tool",
                "content": tool_result,
            })

    return result


# ---------------------------------------------------------------------------
# requests backend (raw Ollama HTTP API)
# ---------------------------------------------------------------------------

def run_with_requests(
    host: str,
    model: str,
    messages: list[dict],
    tools: list[dict],
    api_key: str = "",
    max_tool_rounds: int = 10,
) -> StreamResult:
    """
    Drive a tool-use conversation loop using direct HTTP requests to Ollama API.
    Streams JSON lines and intercepts tool calls as they arrive.
    """
    import requests as req

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    result = StreamResult()
    history = list(messages)

    for _ in range(max_tool_rounds):
        response = req.post(
            f"{host}/api/chat",
            headers=headers,
            json={"model": model, "messages": history, "tools": tools, "stream": True},
            stream=True,
        )
        response.raise_for_status()

        accumulated_text = ""
        pending_tool_calls: list[dict] = []

        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            try:
                chunk = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            msg = chunk.get("message", {})
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls") or []

            if content:
                accumulated_text += content
                result.append_text(content)

            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                pending_tool_calls.append({"name": name, "args": args})

        if not pending_tool_calls:
            break

        if accumulated_text:
            history.append({"role": "assistant", "content": accumulated_text})

        for tc in pending_tool_calls:
            name = tc["name"]
            args = tc["args"]
            tool_result = execute_tool(name, args)
            result.record_tool_call(name, args, tool_result)
            history.append({"role": "tool", "content": tool_result})

    return result


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------

def run_llm_with_tools(
    messages: list[dict],
    tools: list[dict],
    *,
    backend: str,
    model: str,
    ollama_host: str = "http://localhost:11434",
    ollama_api_key: str = "",
    ollama_client: Any = None,
    max_tool_rounds: int = 10,
) -> StreamResult:
    """
    Unified interface for both backends.

    Args:
        messages:       Conversation history in OpenAI message format.
        tools:          Tool schemas (TOOL_SCHEMAS from tools.py).
        backend:        'ollama' or 'requests'.
        model:          Model name string.
        ollama_host:    Base URL for Ollama HTTP API (requests backend).
        ollama_api_key: Optional bearer token.
        ollama_client:  Pre-created ollama.Client instance (ollama backend).
        max_tool_rounds: Safety cap on tool call loops.
    """
    if backend == "ollama":
        if ollama_client is None:
            from ollama import Client
            kwargs: dict = {"host": ollama_host}
            if ollama_api_key:
                kwargs["headers"] = {"Authorization": f"Bearer {ollama_api_key}"}
            ollama_client = Client(**kwargs)
        return run_with_ollama_client(ollama_client, model, messages, tools, max_tool_rounds)

    elif backend == "requests":
        return run_with_requests(ollama_host, model, messages, tools, ollama_api_key, max_tool_rounds)

    else:
        raise ValueError(f"Unknown LLM backend: {backend!r}")
