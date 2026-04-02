"""
index_manager.py - INDEX.json maintenance and fast lookup.

INDEX.json structure:
{
  "version": 1,
  "updated_at": "<ISO timestamp>",
  "entities": {
    "<username>": {
      "core": "<relative path> | null",
      "episodic": ["<relative path>", ...],
      "working": ["<relative path>", ...],
      "tags": ["<tag>", ...]
    }
  },
  "tags": {
    "<tag>": ["<relative path>", ...]
  }
}
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .settings import INDEX_FILE, MEMORIES_DIR
from .storage import read_file


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def load_index() -> dict[str, Any]:
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"version": 1, "updated_at": "", "entities": {}, "tags": {}}


def save_index(index: dict[str, Any]) -> None:
    index["updated_at"] = _now_iso()
    INDEX_FILE.write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Entity helpers
# ---------------------------------------------------------------------------

def _ensure_entity(index: dict, username: str) -> dict:
    if username not in index["entities"]:
        index["entities"][username] = {
            "core": None,
            "episodic": [],
            "working": [],
            "tags": [],
        }
    return index["entities"][username]


def register_file(rel_path: str, username: str, layer: str, tags: list[str] | None = None) -> None:
    """Register a newly created file in the index."""
    index = load_index()
    entity = _ensure_entity(index, username)

    if layer == "core":
        entity["core"] = rel_path
    elif layer in ("episodic", "working"):
        bucket: list = entity[layer]
        if rel_path not in bucket:
            bucket.append(rel_path)
    # knowledge layer files are not entity-specific; skip entity registration

    # Tags
    if tags:
        for tag in tags:
            if tag not in entity["tags"]:
                entity["tags"].append(tag)
            tag_list: list = index["tags"].setdefault(tag, [])
            if rel_path not in tag_list:
                tag_list.append(rel_path)

    save_index(index)


def remove_file(rel_path: str) -> None:
    """Remove a file entry from the index (called on deletion)."""
    index = load_index()

    for entity_data in index["entities"].values():
        if entity_data.get("core") == rel_path:
            entity_data["core"] = None
        for bucket_key in ("episodic", "working"):
            bucket: list = entity_data.get(bucket_key, [])
            if rel_path in bucket:
                bucket.remove(rel_path)

    for tag_list in index["tags"].values():
        if rel_path in tag_list:
            tag_list.remove(rel_path)

    save_index(index)


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_entity_files(username: str) -> dict[str, Any] | None:
    """Return the index entry for a username, or None if not found."""
    index = load_index()
    return index["entities"].get(username)


def entity_exists(username: str) -> bool:
    index = load_index()
    return username in index["entities"]


def get_files_by_tag(tag: str) -> list[str]:
    index = load_index()
    return list(index["tags"].get(tag, []))


def all_entities(index: dict | None = None) -> list[str]:
    if index is None:
        index = load_index()
    return list(index["entities"].keys())


# ---------------------------------------------------------------------------
# Rebuild index from disk (recovery / first-run)
# ---------------------------------------------------------------------------

def rebuild_index() -> None:
    """Scan all memory files and rebuild INDEX.json from scratch."""
    index: dict[str, Any] = {"version": 1, "updated_at": "", "entities": {}, "tags": {}}

    for md_file in sorted(MEMORIES_DIR.rglob("*.md")):
        rel_path = md_file.relative_to(MEMORIES_DIR).as_posix()
        try:
            meta, _ = read_file(md_file)
        except Exception:
            continue

        layer = meta.get("layer", "")
        username = meta.get("entity", "")
        tags = meta.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]

        if username:
            entity = _ensure_entity(index, username)
            if layer == "core":
                entity["core"] = rel_path
            elif layer in ("episodic", "working"):
                bucket: list = entity[layer]
                if rel_path not in bucket:
                    bucket.append(rel_path)
            for tag in tags:
                if tag not in entity["tags"]:
                    entity["tags"].append(tag)

        for tag in tags:
            tag_list: list = index["tags"].setdefault(tag, [])
            if rel_path not in tag_list:
                tag_list.append(rel_path)

    save_index(index)
