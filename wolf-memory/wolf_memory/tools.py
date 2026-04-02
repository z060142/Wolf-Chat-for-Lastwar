"""
tools.py - LLM-internal file operation tool definitions and execution.

These tools are passed to the LLM (Ollama) and executed by stream_parser.py
when a tool_call is detected in the stream.

Tool schemas follow the OpenAI / Ollama function-calling format.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .index_manager import register_file
from .settings import MEMORIES_DIR
from .storage import list_files, read_file, write_file, _sanitize_filename, _now_iso


# ---------------------------------------------------------------------------
# Tool schemas (sent to LLM)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List memory file paths matching optional filters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "layer": {
                        "type": "string",
                        "enum": ["core", "episodic", "working", "knowledge"],
                        "description": "Filter by memory layer. Omit to list all layers.",
                    },
                    "entity": {
                        "type": "string",
                        "description": "Filter by entity (username). Omit for all entities.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the full content of a memory file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Relative path to the file, e.g. 'core/player_alpha.md'",
                    },
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create a new memory file in the specified layer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "layer": {
                        "type": "string",
                        "enum": ["core", "episodic", "working", "knowledge"],
                    },
                    "entity": {
                        "type": "string",
                        "description": "Entity (username) this file belongs to. Omit for knowledge layer.",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for categorization.",
                    },
                    "summary": {
                        "type": "string",
                        "description": "One-line summary stored in frontmatter.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Markdown body content of the file.",
                    },
                },
                "required": ["layer", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_file",
            "description": "Overwrite the body of an existing memory file (frontmatter is preserved and updated_at is refreshed).",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Relative path to the file, e.g. 'core/player_alpha.md'",
                    },
                    "content": {
                        "type": "string",
                        "description": "New Markdown body content.",
                    },
                },
                "required": ["file_path", "content"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

def execute_tool(name: str, args: dict[str, Any]) -> str:
    """
    Dispatch a tool call by name and return the result as a string
    (to be fed back to the LLM as a tool result message).
    """
    try:
        if name == "list_files":
            return _tool_list_files(args)
        if name == "read_file":
            return _tool_read_file(args)
        if name == "write_file":
            return _tool_write_file(args)
        if name == "update_file":
            return _tool_update_file(args)
        return f"Unknown tool: {name}"
    except Exception as exc:
        return f"Error executing {name}: {exc}"


def _tool_list_files(args: dict) -> str:
    layer = args.get("layer")
    entity = args.get("entity")
    files = list_files(layer=layer, entity=entity)
    if not files:
        return "No files found."
    return "\n".join(files)


def _tool_read_file(args: dict) -> str:
    file_path = args["file_path"]
    meta, body = read_file(file_path)
    # Return full raw content so LLM can reason about it
    lines = [f"--- {k}: {v}" for k, v in meta.items()]
    lines.append("---")
    lines.append(body)
    return "\n".join(lines)


def _tool_write_file(args: dict) -> str:
    layer: str = args["layer"]
    entity: str = args.get("entity", "")
    tags: list = args.get("tags") or []
    summary: str = args.get("summary", "")
    content: str = args["content"]

    ts = _now_iso()
    ts_slug = ts.replace(":", "-").replace("T", "_")[:16]

    if entity:
        safe_entity = _sanitize_filename(entity)
        filename = f"{layer}/{ts_slug}_{safe_entity}.md"
    else:
        filename = f"{layer}/{ts_slug}.md"

    meta: dict[str, Any] = {
        "layer": layer,
        "created_at": ts,
        "updated_at": ts,
    }
    if entity:
        meta["entity"] = entity
    if tags:
        meta["tags"] = tags
    if summary:
        meta["summary"] = summary

    path = write_file(filename, meta, content)

    # Update index
    register_file(filename, entity or "__global__", layer, tags)

    return f"Created: {filename}"


def _tool_update_file(args: dict) -> str:
    file_path: str = args["file_path"]
    content: str = args["content"]

    meta, _ = read_file(file_path)
    meta["updated_at"] = _now_iso()
    write_file(file_path, meta, content)
    return f"Updated: {file_path}"
