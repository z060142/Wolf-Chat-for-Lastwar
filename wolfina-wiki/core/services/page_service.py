"""Core page CRUD and relation management.

This service has no knowledge of proposals, reviews, or plugins.
It is the single source of truth for page state.
"""

import json
from datetime import datetime, timezone

from sqlalchemy import asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.exceptions import Conflict, NotFound
from core.models.page import Page, PageRelation, PageStatus, RelationType
from core.schemas.page import PageCreate, PageSearchParams, RelationCreate, SortField, SortOrder


async def create_page(db: AsyncSession, data: PageCreate) -> Page:
    existing = await db.scalar(select(Page).where(Page.slug == data.slug))
    if existing:
        raise Conflict(f"Slug '{data.slug}' is already taken.")

    page = Page(
        title=data.title,
        slug=data.slug,
        content=data.content,
        summary=data.summary,
        canonical_facts=json.dumps(data.canonical_facts) if data.canonical_facts is not None else None,
        source_refs=json.dumps(data.source_refs) if data.source_refs is not None else None,
        confidence=data.confidence,
        status=PageStatus.active,
    )
    db.add(page)
    await db.flush()
    return page


async def get_page(db: AsyncSession, page_id: str) -> Page:
    page = await db.scalar(
        select(Page).where(Page.id == page_id).options(selectinload(Page.versions))
    )
    if page is None:
        raise NotFound(f"Page '{page_id}' not found.")
    return page


async def get_page_by_slug(db: AsyncSession, slug: str) -> Page:
    page = await db.scalar(select(Page).where(Page.slug == slug))
    if page is None:
        raise NotFound(f"Page with slug '{slug}' not found.")
    return page


async def update_page_content(
    db: AsyncSession,
    page_id: str,
    *,
    title: str,
    content: str,
    summary: str,
    canonical_facts: str | None = None,
    source_refs: str | None = None,
) -> Page:
    page = await get_page(db, page_id)
    if page.status == PageStatus.archived:
        raise Conflict("Cannot modify an archived page.")
    page.title = title
    page.content = content
    page.summary = summary
    page.canonical_facts = canonical_facts
    page.source_refs = source_refs
    page.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return page


async def archive_page(db: AsyncSession, page_id: str) -> Page:
    page = await get_page(db, page_id)
    page.status = PageStatus.archived
    page.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return page


async def search_pages(db: AsyncSession, params: PageSearchParams) -> list[Page]:
    stmt = select(Page)
    if params.q:
        pattern = f"%{params.q}%"
        stmt = stmt.where(
            (Page.title.ilike(pattern)) | (Page.content.ilike(pattern)) | (Page.summary.ilike(pattern))
        )
    if params.status:
        stmt = stmt.where(Page.status == params.status)
    if params.updated_after:
        stmt = stmt.where(Page.updated_at > params.updated_after)

    # Dynamic sort column + direction.
    sort_col = {
        SortField.updated_at: Page.updated_at,
        SortField.created_at: Page.created_at,
        SortField.title: Page.title,
    }[params.sort_by]
    order_fn = desc if params.sort_order == SortOrder.desc else asc
    stmt = stmt.order_by(order_fn(sort_col)).offset(params.offset).limit(params.limit)

    result = await db.scalars(stmt)
    return list(result.all())


async def add_relation(db: AsyncSession, data: RelationCreate) -> PageRelation:
    # Validate both pages exist.
    for pid in (data.source_page_id, data.target_page_id):
        exists = await db.scalar(select(Page.id).where(Page.id == pid))
        if exists is None:
            raise NotFound(f"Page '{pid}' not found.")

    existing = await db.scalar(
        select(PageRelation).where(
            PageRelation.source_page_id == data.source_page_id,
            PageRelation.target_page_id == data.target_page_id,
            PageRelation.relation_type == data.relation_type,
        )
    )
    if existing:
        raise Conflict("This relation already exists.")

    rel = PageRelation(
        source_page_id=data.source_page_id,
        target_page_id=data.target_page_id,
        relation_type=data.relation_type,
        created_by_agent=data.created_by_agent,
    )
    db.add(rel)
    await db.flush()
    return rel


async def get_related_pages(db: AsyncSession, page_id: str) -> list[Page]:
    stmt = (
        select(Page)
        .join(PageRelation, PageRelation.target_page_id == Page.id)
        .where(PageRelation.source_page_id == page_id)
    )
    result = await db.scalars(stmt)
    return list(result.all())


async def get_children(db: AsyncSession, page_id: str) -> list[Page]:
    stmt = (
        select(Page)
        .join(PageRelation, PageRelation.target_page_id == Page.id)
        .where(
            PageRelation.source_page_id == page_id,
            PageRelation.relation_type == RelationType.child,
        )
    )
    result = await db.scalars(stmt)
    return list(result.all())


async def get_page_relations(db: AsyncSession, page_id: str) -> list[PageRelation]:
    result = await db.scalars(
        select(PageRelation).where(PageRelation.source_page_id == page_id)
    )
    return list(result.all())
