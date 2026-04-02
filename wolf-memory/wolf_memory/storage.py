"""
storage.py - Markdown file read/write with YAML frontmatter.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .settings import LAYERS, MEMORIES_DIR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _sanitize_filename(name: str) -> str:
    """Convert entity name to safe filename segment."""
    return re.sub(r"[^\w\-.]", "_", name).strip("_")


# ---------------------------------------------------------------------------
# Core read/write
# ---------------------------------------------------------------------------

def parse_md(content: str) -> tuple[dict[str, Any], str]:
    """Split a Markdown file into (frontmatter dict, body text)."""
    m = _FRONTMATTER_RE.match(content)
    if m:
        try:
            meta = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            meta = {}
        body = content[m.end():]
    else:
        meta = {}
        body = content
    return meta, body


def build_md(meta: dict[str, Any], body: str) -> str:
    """Combine frontmatter dict and body into a Markdown string."""
    front = yaml.dump(meta, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{front}\n---\n\n{body.lstrip()}"


def read_file(file_path: str | Path) -> tuple[dict[str, Any], str]:
    """Read a memory Markdown file. Returns (meta, body)."""
    path = Path(file_path)
    if not path.is_absolute():
        path = MEMORIES_DIR / path
    content = path.read_text(encoding="utf-8")
    return parse_md(content)


def write_file(file_path: str | Path, meta: dict[str, Any], body: str) -> Path:
    """Write (overwrite) a memory Markdown file. Returns the resolved path."""
    path = Path(file_path)
    if not path.is_absolute():
        path = MEMORIES_DIR / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_md(meta, body), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# High-level helpers
# ---------------------------------------------------------------------------

def new_working_file(
    username: str,
    timestamp: str,
    user_input: str,
    bot_thoughts: str,
    bot_output: str,
) -> Path:
    """
    Create a new working-layer file for a single interaction.
    Returns the relative path (relative to MEMORIES_DIR).
    """
    safe_name = _sanitize_filename(username)
    ts_slug = timestamp.replace(":", "-").replace("T", "_")[:16]  # 2026-03-29_14-00
    filename = f"working/{ts_slug}_{safe_name}.md"

    meta = {
        "layer": "working",
        "entity": username,
        "created_at": timestamp,
    }
    body = (
        f"**User:** {user_input}\n"
        f"**Thoughts:** {bot_thoughts}\n"
        f"**Bot:** {bot_output}\n"
    )

    write_file(filename, meta, body)
    return Path(filename)


def ensure_layer_dirs() -> None:
    """Make sure all four layer directories exist."""
    for layer in LAYERS:
        (MEMORIES_DIR / layer).mkdir(parents=True, exist_ok=True)


def list_files(
    layer: str | None = None,
    entity: str | None = None,
) -> list[str]:
    """
    List memory file paths (relative to MEMORIES_DIR) matching filters.
    Paths use forward slashes for consistency.
    """
    base = MEMORIES_DIR
    layers = [layer] if layer else LAYERS
    results: list[str] = []

    for lyr in layers:
        lyr_dir = base / lyr
        if not lyr_dir.exists():
            continue
        for md_file in sorted(lyr_dir.glob("*.md")):
            if entity:
                # Quick filter: read frontmatter only
                try:
                    meta, _ = read_file(md_file)
                    if meta.get("entity") != entity:
                        continue
                except Exception:
                    continue
            results.append(f"{lyr}/{md_file.name}")

    return results
