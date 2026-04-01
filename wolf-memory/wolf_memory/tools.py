"""
Document operation tools available to the internal LLM.

Each tool is a plain Python function that returns a dict.
Tool definitions (for Ollama tool_call format) are exported as TOOL_DEFINITIONS.
"""

from pathlib import Path

from . import storage


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def list_files(layer: str | None = None, username: str | None = None) -> dict:
    """
    List available memory file paths.
    - layer: 'archive' | 'persona' | 'compact' | None (all)
    - username: filter to a specific user's files
    """
    results = []

    if layer in (None, "archive"):
        for p in storage.list_archive_files():
            results.append({"path": str(p), "type": "archive"})

    if username:
        users = [username]
    else:
        users = storage.list_users()

    for u in users:
        if layer in (None, "persona"):
            p = storage.persona_path(u)
            if p.exists():
                results.append({"path": str(p), "type": "persona", "username": u})
        if layer in (None, "compact"):
            p = storage.compact_path(u)
            if p.exists():
                results.append({"path": str(p), "type": "compact", "username": u})

    return {"files": results}


def read_file(file_path: str) -> dict:
    """Read the full content of a memory file (frontmatter + body)."""
    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}
    try:
        text = path.read_text(encoding="utf-8")
        return {"path": file_path, "content": text}
    except Exception as e:
        return {"error": str(e)}


def write_file(
    content: str,
    file_type: str,
    username: str | None = None,
    summary: str = "",
) -> dict:
    """
    Create or overwrite a memory file.
    - file_type: 'persona' | 'compact' | 'archive'
    - username: required for persona and compact
    - summary: short description stored in frontmatter
    """
    try:
        if file_type == "persona":
            if not username:
                return {"error": "username required for persona"}
            storage.write_persona(username, content, {"summary": summary} if summary else None)
            return {"path": str(storage.persona_path(username))}

        if file_type == "compact":
            if not username:
                return {"error": "username required for compact"}
            storage.write_compact(username, content)
            return {"path": str(storage.compact_path(username))}

        if file_type == "archive":
            seq = storage.next_archive_sequence()
            path = storage.save_archive(content, seq)
            return {"path": str(path)}

        return {"error": f"Unknown file_type: {file_type}"}
    except Exception as e:
        return {"error": str(e)}


def update_file(file_path: str, content: str) -> dict:
    """Overwrite only the body of an existing MD file, preserving frontmatter."""
    import frontmatter as fm

    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}
    try:
        post = fm.load(str(path))
        post.content = content
        path.write_text(fm.dumps(post), encoding="utf-8")
        return {"path": file_path}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

TOOL_FUNCTIONS = {
    "list_files": list_files,
    "read_file": read_file,
    "write_file": write_file,
    "update_file": update_file,
}


def dispatch(name: str, args: dict) -> dict:
    fn = TOOL_FUNCTIONS.get(name)
    if not fn:
        return {"error": f"Unknown tool: {name}"}
    return fn(**args)


# ---------------------------------------------------------------------------
# Tool definitions (Ollama format)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List available memory file paths, optionally filtered by type or username.",
            "parameters": {
                "type": "object",
                "properties": {
                    "layer": {
                        "type": "string",
                        "enum": ["archive", "persona", "compact"],
                        "description": "File type to filter. Omit for all.",
                    },
                    "username": {
                        "type": "string",
                        "description": "Limit results to this user. Omit for all users.",
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
                        "description": "Absolute path to the file.",
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
            "description": "Create or overwrite a memory file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "file_type": {
                        "type": "string",
                        "enum": ["persona", "compact", "archive"],
                    },
                    "username": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["content", "file_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_file",
            "description": "Overwrite the body of an existing memory file, keeping frontmatter.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["file_path", "content"],
            },
        },
    },
]
