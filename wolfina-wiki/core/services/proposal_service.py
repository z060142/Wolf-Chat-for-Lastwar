"""Proposal workflow: propose → review → apply.

Role-separation rules enforced here:
  - proposer ≠ reviewer
  - executor ≠ proposer AND executor ≠ reviewer
  - A reviewer may not review the same proposal twice.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.events.event_bus import event_bus
from core.events.event_types import Event, EventType
from core.exceptions import Conflict, InvalidTransition, NotFound, RoleViolation
from core.models.proposal import EditProposal, ProposalReview, ProposalStatus, ReviewDecision
from core.schemas.proposal import ApplyRequest, ProposalCreate, ReviewRequest
from core.services import page_service, version_service
from core.settings import settings


async def create_proposal(db: AsyncSession, data: ProposalCreate) -> EditProposal:
    # --- Idempotency check (must be first) ---
    # If the caller supplies an idempotency_key and we already have a proposal with that
    # key, return it immediately without creating a duplicate.  This handles agent retries
    # gracefully regardless of the original proposal's current status.
    if data.idempotency_key:
        existing = await db.scalar(
            select(EditProposal)
            .where(EditProposal.idempotency_key == data.idempotency_key)
            .options(selectinload(EditProposal.reviews))
        )
        if existing:
            return existing

    # Prevent the same agent from having two concurrent pending proposals for one page.
    if data.target_page_id:
        exists = await db.scalar(
            select(EditProposal.id).where(
                EditProposal.target_page_id == data.target_page_id,
                EditProposal.proposer_agent_id == data.proposer_agent_id,
                EditProposal.status == ProposalStatus.pending,
            )
        )
        if exists:
            raise Conflict(
                "This agent already has a pending proposal for that page. "
                "Cancel it before submitting a new one."
            )

    proposal = EditProposal(
        target_page_id=data.target_page_id,
        proposed_title=data.proposed_title,
        proposed_slug=data.proposed_slug,
        proposed_content=data.proposed_content,
        proposed_summary=data.proposed_summary,
        proposed_canonical_facts=data.proposed_canonical_facts,
        proposed_source_refs=data.proposed_source_refs,
        rationale=data.rationale,
        proposer_agent_id=data.proposer_agent_id,
        status=ProposalStatus.pending,
        idempotency_key=data.idempotency_key,
        source_session_id=data.source_session_id,
        batch_id=data.batch_id,
    )
    db.add(proposal)
    await db.flush()

    # Re-fetch with eager-loaded reviews so serialization outside the session works.
    proposal = await get_proposal(db, proposal.id)

    event_bus.emit(
        Event(
            type=EventType.proposal_created,
            payload={
                "proposal_id": proposal.id,
                "proposer": data.proposer_agent_id,
                "batch_id": data.batch_id,
                "source_session_id": data.source_session_id,
            },
        )
    )
    return proposal


async def get_proposal(db: AsyncSession, proposal_id: str) -> EditProposal:
    proposal = await db.scalar(
        select(EditProposal)
        .where(EditProposal.id == proposal_id)
        .options(selectinload(EditProposal.reviews))
    )
    if proposal is None:
        raise NotFound(f"Proposal '{proposal_id}' not found.")
    return proposal


async def list_proposals(
    db: AsyncSession,
    *,
    page_id: str | None = None,
    status: ProposalStatus | None = None,
    proposer_agent_id: str | None = None,
    batch_id: str | None = None,
    source_session_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[EditProposal]:
    stmt = select(EditProposal).options(selectinload(EditProposal.reviews))
    if page_id:
        stmt = stmt.where(EditProposal.target_page_id == page_id)
    if status:
        stmt = stmt.where(EditProposal.status == status)
    if proposer_agent_id:
        stmt = stmt.where(EditProposal.proposer_agent_id == proposer_agent_id)
    if batch_id:
        stmt = stmt.where(EditProposal.batch_id == batch_id)
    if source_session_id:
        stmt = stmt.where(EditProposal.source_session_id == source_session_id)
    stmt = stmt.order_by(EditProposal.created_at.desc()).offset(offset).limit(limit)
    result = await db.scalars(stmt)
    return list(result.all())


async def review_proposal(db: AsyncSession, proposal_id: str, data: ReviewRequest) -> EditProposal:
    proposal = await get_proposal(db, proposal_id)

    if proposal.status != ProposalStatus.pending:
        raise InvalidTransition(f"Proposal is '{proposal.status}', not pending.")

    if data.reviewer_agent_id == proposal.proposer_agent_id:
        raise RoleViolation("Reviewer cannot be the same agent as the proposer.")

    already_reviewed = any(r.reviewer_agent_id == data.reviewer_agent_id for r in proposal.reviews)
    if already_reviewed:
        raise Conflict("This reviewer has already submitted a decision on this proposal.")

    review = ProposalReview(
        proposal_id=proposal.id,
        reviewer_agent_id=data.reviewer_agent_id,
        decision=data.decision,
        feedback=data.feedback,
    )
    db.add(review)
    await db.flush()

    # Expire and refresh to pick up the newly flushed review from the DB.
    await db.refresh(proposal, ["reviews"])
    approval_count = sum(1 for r in proposal.reviews if r.decision == ReviewDecision.approve)
    rejection_count = sum(1 for r in proposal.reviews if r.decision == ReviewDecision.reject)

    if rejection_count > 0:
        proposal.status = ProposalStatus.rejected
    elif approval_count >= settings.min_reviewers:
        proposal.status = ProposalStatus.approved

    await db.flush()

    event_bus.emit(
        Event(
            type=EventType.proposal_reviewed,
            payload={
                "proposal_id": proposal.id,
                "decision": data.decision,
                "reviewer": data.reviewer_agent_id,
                "new_status": proposal.status,
            },
        )
    )
    return proposal


async def apply_proposal(db: AsyncSession, proposal_id: str, data: ApplyRequest) -> EditProposal:
    # Use with_for_update() to serialize concurrent apply attempts at the DB level.
    # The second executor that races on the same proposal will see status='applied'
    # once the first commits, and will get an InvalidTransition error cleanly.
    proposal = await db.scalar(
        select(EditProposal)
        .where(EditProposal.id == proposal_id)
        .options(selectinload(EditProposal.reviews))
        .with_for_update()
    )
    if proposal is None:
        raise NotFound(f"Proposal '{proposal_id}' not found.")

    if proposal.status != ProposalStatus.approved:
        raise InvalidTransition(f"Proposal is '{proposal.status}', expected 'approved'.")

    reviewer_ids = {r.reviewer_agent_id for r in proposal.reviews}
    if data.executor_agent_id == proposal.proposer_agent_id:
        raise RoleViolation("Executor cannot be the same agent as the proposer.")
    if data.executor_agent_id in reviewer_ids:
        raise RoleViolation("Executor cannot be one of the reviewers.")

    if proposal.target_page_id:
        # Edit existing page.
        page = await page_service.update_page_content(
            db,
            proposal.target_page_id,
            title=proposal.proposed_title,
            content=proposal.proposed_content,
            summary=proposal.proposed_summary,
            canonical_facts=proposal.proposed_canonical_facts,
            source_refs=proposal.proposed_source_refs,
        )
        event_type = EventType.page_updated
    else:
        # Create new page from proposal.
        from core.schemas.page import PageCreate

        page = await page_service.create_page(
            db,
            PageCreate(
                title=proposal.proposed_title,
                slug=proposal.proposed_slug or _slugify(proposal.proposed_title),
                content=proposal.proposed_content,
                summary=proposal.proposed_summary,
                creator_agent_id=data.executor_agent_id,
                creation_reason=proposal.rationale,
            ),
        )
        proposal.target_page_id = page.id
        event_type = EventType.page_created

    await version_service.snapshot_page(
        db,
        page,
        editor_agent_id=data.executor_agent_id,
        edit_reason=proposal.rationale,
        proposal_id=proposal.id,
    )

    proposal.status = ProposalStatus.applied
    await db.flush()

    event_bus.emit(
        Event(
            type=EventType.proposal_applied,
            payload={
                "proposal_id": proposal.id,
                "page_id": page.id,
                "executor": data.executor_agent_id,
                "batch_id": proposal.batch_id,
                "source_session_id": proposal.source_session_id,
            },
        )
    )
    event_bus.emit(Event(type=event_type, payload={"page_id": page.id}))
    return proposal


async def cancel_proposal(db: AsyncSession, proposal_id: str, agent_id: str) -> EditProposal:
    proposal = await get_proposal(db, proposal_id)
    if proposal.status not in (ProposalStatus.pending, ProposalStatus.approved):
        raise InvalidTransition(f"Cannot cancel a proposal with status '{proposal.status}'.")
    if proposal.proposer_agent_id != agent_id:
        raise RoleViolation("Only the original proposer may cancel a proposal.")
    proposal.status = ProposalStatus.cancelled
    await db.flush()
    return proposal


def _slugify(title: str) -> str:
    import re
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug[:512]
