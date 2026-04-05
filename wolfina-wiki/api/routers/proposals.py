from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_agent, get_db, map_wiki_error
from core.exceptions import WikiError
from core.models.proposal import ProposalStatus
from core.schemas.proposal import ApplyRequest, ProposalCreate, ProposalRead, ReviewRequest
from core.services import proposal_service

router = APIRouter(prefix="/proposals", tags=["proposals"])


@router.post("", response_model=ProposalRead, status_code=201)
async def create_proposal(
    body: ProposalCreate,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
) -> ProposalRead:
    try:
        proposal = await proposal_service.create_proposal(db, body)
        return ProposalRead.model_validate(proposal)
    except WikiError as exc:
        raise map_wiki_error(exc) from exc


@router.get("", response_model=list[ProposalRead])
async def list_proposals(
    page_id: str | None = Query(None, description="Filter by target page ID"),
    status: ProposalStatus | None = Query(None),
    proposer_agent_id: str | None = Query(None, description="Filter by proposer agent"),
    batch_id: str | None = Query(None, description="Filter by batch ID"),
    source_session_id: str | None = Query(None, description="Filter by source session ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
) -> list[ProposalRead]:
    proposals = await proposal_service.list_proposals(
        db,
        page_id=page_id,
        status=status,
        proposer_agent_id=proposer_agent_id,
        batch_id=batch_id,
        source_session_id=source_session_id,
        limit=limit,
        offset=offset,
    )
    return [ProposalRead.model_validate(p) for p in proposals]


@router.get("/{proposal_id}", response_model=ProposalRead)
async def get_proposal(
    proposal_id: str,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
) -> ProposalRead:
    try:
        proposal = await proposal_service.get_proposal(db, proposal_id)
        return ProposalRead.model_validate(proposal)
    except WikiError as exc:
        raise map_wiki_error(exc) from exc


@router.post("/{proposal_id}/review", response_model=ProposalRead)
async def review_proposal(
    proposal_id: str,
    body: ReviewRequest,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
) -> ProposalRead:
    try:
        proposal = await proposal_service.review_proposal(db, proposal_id, body)
        return ProposalRead.model_validate(proposal)
    except WikiError as exc:
        raise map_wiki_error(exc) from exc


@router.post("/{proposal_id}/apply", response_model=ProposalRead)
async def apply_proposal(
    proposal_id: str,
    body: ApplyRequest,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
) -> ProposalRead:
    try:
        proposal = await proposal_service.apply_proposal(db, proposal_id, body)
        return ProposalRead.model_validate(proposal)
    except WikiError as exc:
        raise map_wiki_error(exc) from exc


@router.post("/{proposal_id}/cancel", response_model=ProposalRead)
async def cancel_proposal(
    proposal_id: str,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
) -> ProposalRead:
    try:
        proposal = await proposal_service.cancel_proposal(db, proposal_id, agent_id)
        return ProposalRead.model_validate(proposal)
    except WikiError as exc:
        raise map_wiki_error(exc) from exc
