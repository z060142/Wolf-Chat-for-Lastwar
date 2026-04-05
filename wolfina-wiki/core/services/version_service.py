"""Version history management."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.page import Page, PageVersion


async def snapshot_page(
    db: AsyncSession,
    page: Page,
    *,
    editor_agent_id: str,
    edit_reason: str,
    proposal_id: str | None = None,
) -> PageVersion:
    """Capture the current state of *page* as a new version row."""
    max_version = await db.scalar(
        select(func.max(PageVersion.version_number)).where(PageVersion.page_id == page.id)
    )
    next_version = (max_version or 0) + 1

    version = PageVersion(
        page_id=page.id,
        version_number=next_version,
        title=page.title,
        content=page.content,
        summary=page.summary,
        editor_agent_id=editor_agent_id,
        edit_reason=edit_reason,
        proposal_id=proposal_id,
    )
    db.add(version)
    await db.flush()
    return version


async def get_history(db: AsyncSession, page_id: str) -> list[PageVersion]:
    result = await db.scalars(
        select(PageVersion)
        .where(PageVersion.page_id == page_id)
        .order_by(PageVersion.version_number.desc())
    )
    return list(result.all())
