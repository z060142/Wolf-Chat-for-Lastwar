from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_agent, get_db, map_wiki_error
from core.exceptions import WikiError
from core.models.page import PageStatus
from core.schemas.page import (
    PageCreate,
    PageRead,
    PageSearchParams,
    PageVersionRead,
    RelationCreate,
    RelationRead,
    SortField,
    SortOrder,
)
from core.services import page_service, version_service

router = APIRouter(prefix="/pages", tags=["pages"])


@router.post("", response_model=PageRead, status_code=201)
async def create_page(
    body: PageCreate,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
) -> PageRead:
    try:
        page = await page_service.create_page(db, body)
        return PageRead.model_validate(page)
    except WikiError as exc:
        raise map_wiki_error(exc) from exc


@router.get("/search", response_model=list[PageRead])
async def search_pages(
    q: str = Query(""),
    status: PageStatus | None = Query(None),
    updated_after: datetime | None = Query(None, description="ISO-8601 datetime; return pages updated after this timestamp"),
    sort_by: SortField = Query(SortField.updated_at),
    sort_order: SortOrder = Query(SortOrder.desc),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
) -> list[PageRead]:
    params = PageSearchParams(
        q=q,
        status=status,
        updated_after=updated_after,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )
    pages = await page_service.search_pages(db, params)
    return [PageRead.model_validate(p) for p in pages]


# Must appear before /{page_id} to avoid being swallowed by the catch-all.
@router.get("/by-slug/{slug}", response_model=PageRead)
async def get_page_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
) -> PageRead:
    try:
        page = await page_service.get_page_by_slug(db, slug)
        return PageRead.model_validate(page)
    except WikiError as exc:
        raise map_wiki_error(exc) from exc


@router.get("/{page_id}", response_model=PageRead)
async def get_page(
    page_id: str,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
) -> PageRead:
    try:
        page = await page_service.get_page(db, page_id)
        return PageRead.model_validate(page)
    except WikiError as exc:
        raise map_wiki_error(exc) from exc


@router.post("/{page_id}/archive", response_model=PageRead)
async def archive_page(
    page_id: str,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
) -> PageRead:
    try:
        page = await page_service.archive_page(db, page_id)
        return PageRead.model_validate(page)
    except WikiError as exc:
        raise map_wiki_error(exc) from exc


@router.get("/{page_id}/related", response_model=list[PageRead])
async def get_related_pages(
    page_id: str,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
) -> list[PageRead]:
    try:
        pages = await page_service.get_related_pages(db, page_id)
        return [PageRead.model_validate(p) for p in pages]
    except WikiError as exc:
        raise map_wiki_error(exc) from exc


@router.get("/{page_id}/children", response_model=list[PageRead])
async def get_children(
    page_id: str,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
) -> list[PageRead]:
    try:
        pages = await page_service.get_children(db, page_id)
        return [PageRead.model_validate(p) for p in pages]
    except WikiError as exc:
        raise map_wiki_error(exc) from exc


@router.get("/{page_id}/relations", response_model=list[RelationRead])
async def get_page_relations(
    page_id: str,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
) -> list[RelationRead]:
    try:
        relations = await page_service.get_page_relations(db, page_id)
        return [RelationRead.model_validate(r) for r in relations]
    except WikiError as exc:
        raise map_wiki_error(exc) from exc


@router.get("/{page_id}/history", response_model=list[PageVersionRead])
async def get_history(
    page_id: str,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
) -> list[PageVersionRead]:
    try:
        await page_service.get_page(db, page_id)  # ensure page exists
        versions = await version_service.get_history(db, page_id)
        return [PageVersionRead.model_validate(v) for v in versions]
    except WikiError as exc:
        raise map_wiki_error(exc) from exc


@router.post("/relations", response_model=RelationRead, status_code=201)
async def add_relation(
    body: RelationCreate,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
) -> RelationRead:
    try:
        rel = await page_service.add_relation(db, body)
        return RelationRead.model_validate(rel)
    except WikiError as exc:
        raise map_wiki_error(exc) from exc
