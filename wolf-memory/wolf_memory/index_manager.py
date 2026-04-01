"""
INDEX.json manager.

Tracks per-user state:
  - conversation counter (for persona update trigger)
  - compact dirty flag (for lazy compact refresh)
  - compact last updated timestamp
  - window entry count (for archive trigger)
"""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from .config import INDEX_FILE, MEMORIES_DIR, WINDOW_MAX_ENTRIES


_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Internal load/save
# ---------------------------------------------------------------------------

def _default_index() -> dict:
    return {
        "version": 1,
        "updated_at": _now_iso(),
        "window_entry_count": 0,
        "users": {},
    }


def _default_user() -> dict:
    return {
        "convo_count": 0,
        "persona_last_updated_at_count": 0,   # convo_count value at last persona update
        "compact_dirty": False,
        "compact_last_updated": None,
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def load() -> dict:
    if not INDEX_FILE.exists():
        return _default_index()
    with open(INDEX_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save(index: dict) -> None:
    index["updated_at"] = _now_iso()
    MEMORIES_DIR.mkdir(parents=True, exist_ok=True)
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Window entry count
# ---------------------------------------------------------------------------

def get_window_count() -> int:
    return load().get("window_entry_count", 0)


def increment_window_count() -> int:
    """Increment global window entry count. Returns new count."""
    with _lock:
        index = load()
        count = index.get("window_entry_count", 0) + 1
        index["window_entry_count"] = count
        _save(index)
    return count


def reset_window_count() -> None:
    with _lock:
        index = load()
        index["window_entry_count"] = 0
        _save(index)


def window_is_full() -> bool:
    return get_window_count() >= WINDOW_MAX_ENTRIES


# ---------------------------------------------------------------------------
# Per-user state
# ---------------------------------------------------------------------------

def get_user(username: str) -> dict:
    index = load()
    return dict(index.get("users", {}).get(username, _default_user()))


def _update_user(username: str, updates: dict) -> None:
    with _lock:
        index = load()
        users = index.setdefault("users", {})
        user = dict(users.get(username, _default_user()))
        user.update(updates)
        users[username] = user
        _save(index)


def user_exists(username: str) -> bool:
    return username in load().get("users", {})


def register_user(username: str) -> None:
    """Add a new user entry if not already present."""
    if not user_exists(username):
        _update_user(username, {})


def record_conversation(username: str) -> dict:
    """
    Increment conversation count for a user and mark compact as dirty.
    Returns updated user state dict.
    """
    with _lock:
        index = load()
        users = index.setdefault("users", {})
        user = dict(users.get(username, _default_user()))
        user["convo_count"] = user.get("convo_count", 0) + 1
        user["compact_dirty"] = True
        users[username] = user
        _save(index)
    return dict(user)


def should_update_persona(username: str, interval: int) -> bool:
    """
    Return True if the user's convo_count has advanced by at least `interval`
    since the last persona update.
    """
    user = get_user(username)
    count = user.get("convo_count", 0)
    last = user.get("persona_last_updated_at_count", 0)
    return (count - last) >= interval


def mark_persona_updated(username: str) -> None:
    user = get_user(username)
    _update_user(username, {
        "persona_last_updated_at_count": user.get("convo_count", 0)
    })


def mark_compact_updated(username: str) -> None:
    _update_user(username, {
        "compact_dirty": False,
        "compact_last_updated": _now_iso(),
    })


def compact_needs_refresh(username: str, min_interval_hours: float) -> bool:
    """
    Return True if compact is dirty AND enough time has passed since last update.
    """
    user = get_user(username)
    if not user.get("compact_dirty", False):
        return False
    last_str = user.get("compact_last_updated")
    if not last_str:
        return True
    last = datetime.fromisoformat(last_str).replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - last).total_seconds() / 3600
    return elapsed >= min_interval_hours


def get_all_dirty_users() -> list[str]:
    """Return list of usernames with compact_dirty=True."""
    index = load()
    return [
        u for u, data in index.get("users", {}).items()
        if data.get("compact_dirty", False)
    ]


def reconcile_on_startup() -> None:
    """
    Called once at subprocess startup.
    Reconciles INDEX.json with the actual state of files on disk so that
    counters and timestamps survive process restarts and crashes.

    What it does:
    - Syncs window_entry_count with the actual number of entries in window.md
    - Registers any user directories found on disk that are missing from INDEX.json
    - Syncs compact_last_updated from compact.md frontmatter (authoritative source)
    - Marks compact_dirty=True for users whose compact.md is older than window.md
      (ensures a refresh is scheduled even if the process died mid-update)
    """
    from . import storage  # local import to avoid circular at module level

    with _lock:
        index = load()

        # 1. Sync window_entry_count from actual window.md content
        actual_count = storage.count_window_entries(storage.read_window())
        index["window_entry_count"] = actual_count

        # 2. Discover users from disk
        users = index.setdefault("users", {})
        for user_dir in storage.USERS_DIR.iterdir() if storage.USERS_DIR.exists() else []:
            if not user_dir.is_dir():
                continue
            username = user_dir.name
            if username not in users:
                users[username] = _default_user()

        # 3. Sync compact_last_updated from compact.md frontmatter
        window_mtime = (
            storage.WINDOW_FILE.stat().st_mtime
            if storage.WINDOW_FILE.exists() else 0
        )
        for username, user_data in users.items():
            compact_post = storage.read_compact(username)
            if compact_post:
                ts_str = compact_post.metadata.get("updated_at")
                if ts_str:
                    user_data["compact_last_updated"] = ts_str
                    # If window.md is newer than compact.md, mark dirty
                    try:
                        compact_ts = datetime.fromisoformat(ts_str).timestamp()
                        if window_mtime > compact_ts:
                            user_data["compact_dirty"] = True
                    except ValueError:
                        user_data["compact_dirty"] = True
                else:
                    user_data["compact_dirty"] = True
            else:
                # No compact.md exists yet — mark dirty so it gets created
                user_data["compact_dirty"] = True

        _save(index)
    import sys
    print(f"[WolfMemory] Startup reconciliation complete. window_entries={actual_count}, users={len(users)}",
          file=sys.stderr, flush=True)
