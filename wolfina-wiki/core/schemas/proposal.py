from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from core.models.proposal import ProposalStatus, ReviewDecision


class ProposalCreate(BaseModel):
    # Null = create a new page.
    target_page_id: str | None = None
    proposed_title: str = Field(..., min_length=1, max_length=512)
    proposed_slug: str | None = Field(
        None, min_length=1, max_length=512, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    proposed_content: str = ""
    proposed_summary: str = ""
    proposed_canonical_facts: str | None = None
    proposed_source_refs: str | None = None
    rationale: str = Field(..., min_length=1)
    proposer_agent_id: str = Field(..., min_length=1)

    # --- Traceability / idempotency ---
    # Supply a stable key (e.g. hash of content) so retries return the existing proposal.
    idempotency_key: str | None = Field(None, max_length=256)
    # Which agent session/conversation window produced this proposal.
    source_session_id: str | None = Field(None, max_length=256)
    # Groups proposals submitted together from one reasoning run.
    batch_id: str | None = Field(None, max_length=256)


class ReviewRequest(BaseModel):
    reviewer_agent_id: str = Field(..., min_length=1)
    decision: ReviewDecision
    feedback: str | None = None


class ApplyRequest(BaseModel):
    executor_agent_id: str = Field(..., min_length=1)


class ProposalReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    proposal_id: str
    reviewer_agent_id: str
    decision: ReviewDecision
    feedback: str | None
    reviewed_at: datetime


class ProposalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    target_page_id: str | None
    proposed_title: str
    proposed_slug: str | None
    proposed_content: str
    proposed_summary: str
    proposed_canonical_facts: str | None
    proposed_source_refs: str | None
    rationale: str
    proposer_agent_id: str
    status: ProposalStatus
    idempotency_key: str | None
    source_session_id: str | None
    batch_id: str | None
    created_at: datetime
    updated_at: datetime
    reviews: list[ProposalReviewRead] = []
