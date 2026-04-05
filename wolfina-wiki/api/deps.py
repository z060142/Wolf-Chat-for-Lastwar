from collections.abc import AsyncGenerator

from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.session import get_db as _get_db
from core.exceptions import Conflict, InvalidTransition, NotFound, PluginError, RoleViolation


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in _get_db():
        yield session


def get_current_agent(x_agent_id: str = Header(..., description="Unique identifier for the calling agent")) -> str:
    if not x_agent_id.strip():
        raise HTTPException(status_code=400, detail="X-Agent-ID header must not be empty.")
    return x_agent_id.strip()


def map_wiki_error(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, Conflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, RoleViolation):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, InvalidTransition):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, PluginError):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=500, detail="Internal server error.")
