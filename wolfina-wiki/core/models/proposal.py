import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class ProposalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    applied = "applied"
    cancelled = "cancelled"


class ReviewDecision(str, Enum):
    approve = "approve"
    reject = "reject"


class EditProposal(Base):
    __tablename__ = "edit_proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # Null when proposing a brand-new page.
    target_page_id: Mapped[str | None] = mapped_column(
        ForeignKey("pages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    proposed_title: Mapped[str] = mapped_column(String(512), nullable=False)
    proposed_slug: Mapped[str | None] = mapped_column(String(512), nullable=True)
    proposed_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    proposed_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    proposed_canonical_facts: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_source_refs: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    proposer_agent_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=ProposalStatus.pending)

    # --- Traceability metadata ---
    # Caller-supplied key for idempotent submission. Same key → return existing proposal.
    idempotency_key: Mapped[str | None] = mapped_column(String(256), nullable=True, unique=True, index=True)
    # Which agent session (conversation window) generated this proposal.
    source_session_id: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    # Groups multiple proposals submitted together from one reasoning run.
    batch_id: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    reviews: Mapped[list["ProposalReview"]] = relationship(
        "ProposalReview", back_populates="proposal", cascade="all, delete-orphan", order_by="ProposalReview.reviewed_at"
    )


class ProposalReview(Base):
    __tablename__ = "proposal_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    proposal_id: Mapped[str] = mapped_column(
        ForeignKey("edit_proposals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewer_agent_id: Mapped[str] = mapped_column(String(256), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    proposal: Mapped["EditProposal"] = relationship("EditProposal", back_populates="reviews")
