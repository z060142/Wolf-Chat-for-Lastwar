"""Shared pytest fixtures for the Wolfina Wiki test suite."""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.db.base import Base, import_models


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Fresh in-memory SQLite engine per test."""
    import_models()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine):
    """Async session bound to the test engine."""
    factory = async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def client(db_engine):
    """Test HTTP client with test DB engine injected via dependency override."""
    # Import inside fixture to avoid premature module-level side-effects.
    import api.deps as deps
    from api.app import create_app

    app = create_app()
    factory = async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)

    async def override_get_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # Override the function that routers actually depend on (api.deps.get_db).
    app.dependency_overrides[deps.get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
