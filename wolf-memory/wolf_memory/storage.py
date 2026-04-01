"""
MD file read/write operations for wolf-memory.
All memory files use YAML frontmatter via python-frontmatter.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import frontmatter

from .config import (
    ARCHIVE_DIR,
    MEMORIES_DIR,
    USERS_DIR,
    WINDOW_FILE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _user_dir(username: str) -> Path:
    return USERS_DIR / _safe_name(username)


def _safe_name(name: str) -> str:
    """Convert username to a filesystem-safe directory/file name."""
    safe = "".join(c if (c.isalnum() or c in "-_. ") else "_" for c in name)
    return safe.strip()


# ---------------------------------------------------------------------------
# Window (shared public chat window)
# ---------------------------------------------------------------------------

WINDOW_SEPARATOR = "---"


def read_window() -> str:
    """Return raw window.md content, or empty string if not yet created."""
    if not WINDOW_FILE.exists():
        return ""
    return WINDOW_FILE.read_text(encoding="utf-8")


def count_window_entries(content: str) -> int:
    """Count the number of conversation entries (separated by ---)."""
    if not content.strip():
        return 0
    return content.count(f"\n{WINDOW_SEPARATOR}\n") + (
        1 if content.strip() else 0
    )


def append_to_window(entry: str) -> int:
    """
    Append a conversation entry to window.md.
    Returns the new total entry count.
    """
    import sys
    _ensure_dir(MEMORIES_DIR)
    current = read_window()

    if current.strip():
        new_content = current.rstrip() + f"\n{WINDOW_SEPARATOR}\n" + entry.strip() + "\n"
    else:
        new_content = entry.strip() + "\n"

    WINDOW_FILE.write_text(new_content, encoding="utf-8")
    count = count_window_entries(new_content)
    print(f"[WolfMemory] append_to_window: wrote {len(new_content)} bytes, count={count}, path={WINDOW_FILE}",
          file=sys.stderr, flush=True)
    return count


def reset_window(opening_summary: str = "") -> None:
    """
    Clear window.md and optionally prepend an archive summary as context.
    Called after archiving a full window.
    """
    if opening_summary.strip():
        content = f"[Previous session summary]\n{opening_summary.strip()}\n"
    else:
        content = ""
    WINDOW_FILE.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------

def save_archive(summary: str, sequence: int) -> Path:
    """
    Save an archived window summary.
    Returns the path of the created file.
    """
    _ensure_dir(ARCHIVE_DIR)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"{date_str}_{sequence:03d}.md"
    path = ARCHIVE_DIR / filename

    # Avoid filename collision
    counter = sequence
    while path.exists():
        counter += 1
        path = ARCHIVE_DIR / f"{date_str}_{counter:03d}.md"

    post = frontmatter.Post(
        summary,
        archived_at=_now_iso(),
        sequence=counter,
    )
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return path


def next_archive_sequence() -> int:
    """Return the next available archive sequence number for today."""
    if not ARCHIVE_DIR.exists():
        return 1
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    existing = list(ARCHIVE_DIR.glob(f"{date_str}_*.md"))
    return len(existing) + 1


# ---------------------------------------------------------------------------
# User files: persona and compact
# ---------------------------------------------------------------------------

def _read_md(path: Path) -> frontmatter.Post | None:
    if not path.exists():
        return None
    return frontmatter.load(str(path))


def _write_md(path: Path, post: frontmatter.Post) -> None:
    _ensure_dir(path.parent)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


# --- Persona ---

def persona_path(username: str) -> Path:
    return _user_dir(username) / "persona.md"


def read_persona(username: str) -> frontmatter.Post | None:
    return _read_md(persona_path(username))


def write_persona(username: str, content: str, metadata: dict | None = None) -> None:
    path = persona_path(username)
    existing = _read_md(path)
    meta = dict(existing.metadata) if existing else {}
    meta.update({
        "username": username,
        "updated_at": _now_iso(),
    })
    if metadata:
        meta.update(metadata)
    if "created_at" not in meta:
        meta["created_at"] = _now_iso()
    post = frontmatter.Post(content, **meta)
    _write_md(path, post)


def create_empty_persona(username: str) -> None:
    """Create an empty persona file for a new user."""
    path = persona_path(username)
    if path.exists():
        return
    post = frontmatter.Post(
        "",
        username=username,
        created_at=_now_iso(),
        updated_at=_now_iso(),
    )
    _write_md(path, post)


# --- Compact summary ---

def compact_path(username: str) -> Path:
    return _user_dir(username) / "compact.md"


def read_compact(username: str) -> frontmatter.Post | None:
    return _read_md(compact_path(username))


def write_compact(username: str, content: str) -> None:
    path = compact_path(username)
    post = frontmatter.Post(
        content,
        username=username,
        updated_at=_now_iso(),
    )
    _write_md(path, post)


def compact_last_updated(username: str) -> datetime | None:
    """Return the last updated time of compact.md, or None if not exists."""
    post = read_compact(username)
    if not post:
        return None
    ts = post.metadata.get("updated_at")
    if not ts:
        return None
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# List helpers
# ---------------------------------------------------------------------------

def list_archive_files() -> list[Path]:
    if not ARCHIVE_DIR.exists():
        return []
    return sorted(ARCHIVE_DIR.glob("*.md"))


def list_users() -> list[str]:
    if not USERS_DIR.exists():
        return []
    return [d.name for d in USERS_DIR.iterdir() if d.is_dir()]
