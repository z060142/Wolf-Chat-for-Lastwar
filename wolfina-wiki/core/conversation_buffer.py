"""Thread-safe conversation buffer with configurable trigger conditions.

This module provides a module-level singleton `conversation_buffer` that is
shared between the FastAPI ingest endpoint and the wiki processor / GUI.
"""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from core.settings import settings


@dataclass
class Message:
    id: str
    speaker: str
    content: str
    timestamp: datetime
    processed: bool = False
    processed_at: Optional[datetime] = None


class ConversationBuffer:
    """Thread-safe buffer that accumulates messages and tracks trigger conditions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._messages: list[Message] = []
        self._paused: bool = False

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def add_message(self, speaker: str, content: str, timestamp: Optional[datetime] = None) -> Message:
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        msg = Message(
            id=str(uuid.uuid4()),
            speaker=speaker,
            content=content,
            timestamp=timestamp,
        )
        with self._lock:
            self._messages.append(msg)
        return msg

    def mark_processed(self, message_ids: list[str]) -> None:
        now = datetime.now(timezone.utc)
        id_set = set(message_ids)
        with self._lock:
            for msg in self._messages:
                if msg.id in id_set and not msg.processed:
                    msg.processed = True
                    msg.processed_at = now

    def clear_processed(self) -> int:
        """Remove all processed messages. Returns count removed."""
        with self._lock:
            before = len(self._messages)
            self._messages = [m for m in self._messages if not m.processed]
            return before - len(self._messages)

    def clear_all(self) -> None:
        with self._lock:
            self._messages.clear()

    def set_paused(self, paused: bool) -> None:
        with self._lock:
            self._paused = paused

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_pending_messages(self) -> list[Message]:
        with self._lock:
            return [m for m in self._messages if not m.processed]

    def get_all_messages(self) -> list[Message]:
        with self._lock:
            return list(self._messages)

    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    def get_stats(self) -> dict:
        with self._lock:
            pending = [m for m in self._messages if not m.processed]
            total_chars = sum(len(m.content) for m in pending)
            first_ts = pending[0].timestamp if pending else None
            elapsed = 0.0
            if first_ts:
                elapsed = (datetime.now(timezone.utc) - first_ts).total_seconds()
            return {
                "pending_count": len(pending),
                "total_chars": total_chars,
                "elapsed_sec": elapsed,
                "total_messages": len(self._messages),
                "paused": self._paused,
            }

    def should_trigger(self) -> bool:
        """Return True if any trigger condition is met and buffer is not paused."""
        stats = self.get_stats()
        if stats["paused"]:
            return False
        if stats["pending_count"] == 0:
            return False
        if stats["pending_count"] >= settings.trigger_msg_count:
            return True
        if stats["total_chars"] >= settings.trigger_char_count:
            return True
        if stats["elapsed_sec"] >= settings.trigger_duration_sec:
            return True
        return False


# Module-level singleton — imported by both the API and the GUI/processor.
conversation_buffer = ConversationBuffer()
