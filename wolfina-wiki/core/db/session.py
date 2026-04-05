from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.base import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
