import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class PageStatus(str, Enum):
    active = "active"
    archived = "archived"


class RelationType(str, Enum):
    parent = "parent"
    child = "child"
    related_to = "related_to"
    references = "references"


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    slug: Mapped[str] = mapped_column(String(512), nullable=False, unique=True, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Optional enrichment fields stored as JSON-encoded strings.
    canonical_facts: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_refs: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=PageStatus.active)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    versions: Mapped[list["PageVersion"]] = relationship(
        "PageVersion", back_populates="page", cascade="all, delete-orphan", order_by="PageVersion.version_number"
    )
    outgoing_relations: Mapped[list["PageRelation"]] = relationship(
        "PageRelation",
        foreign_keys="PageRelation.source_page_id",
        back_populates="source_page",
        cascade="all, delete-orphan",
    )
    incoming_relations: Mapped[list["PageRelation"]] = relationship(
        "PageRelation",
        foreign_keys="PageRelation.target_page_id",
        back_populates="target_page",
        cascade="all, delete-orphan",
    )


class PageVersion(Base):
    __tablename__ = "page_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    page_id: Mapped[str] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    editor_agent_id: Mapped[str] = mapped_column(String(256), nullable=False)
    edit_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    proposal_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    page: Mapped["Page"] = relationship("Page", back_populates="versions")


class PageRelation(Base):
    __tablename__ = "page_relations"
    __table_args__ = (
        UniqueConstraint("source_page_id", "target_page_id", "relation_type", name="uq_relation"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_page_id: Mapped[str] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_page_id: Mapped[str] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_by_agent: Mapped[str] = mapped_column(String(256), nullable=False)

    source_page: Mapped["Page"] = relationship("Page", foreign_keys=[source_page_id], back_populates="outgoing_relations")
    target_page: Mapped["Page"] = relationship("Page", foreign_keys=[target_page_id], back_populates="incoming_relations")
