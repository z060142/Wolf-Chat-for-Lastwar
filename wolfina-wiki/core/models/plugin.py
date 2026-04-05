import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class PluginRecord(Base):
    __tablename__ = "plugins"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    # JSON-encoded list of capability strings.
    capabilities: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class PluginEventLog(Base):
    """Audit trail for events emitted through the plugin layer."""

    __tablename__ = "plugin_event_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    plugin_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    # JSON-encoded payload.
    payload: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    source: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="emitted")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
