from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_agent, get_db, map_wiki_error
from core.exceptions import WikiError
from core.schemas.plugin import CapabilityRead, EventEmit, PluginRegister, PluginStatusRead
from core.services import plugin_service

router = APIRouter(prefix="/plugins", tags=["plugins"])


@router.post("", response_model=PluginStatusRead, status_code=201)
async def register_plugin(
    body: PluginRegister,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
) -> PluginStatusRead:
    try:
        record = await plugin_service.register_plugin(db, body)
        return PluginStatusRead.model_validate(record)
    except WikiError as exc:
        raise map_wiki_error(exc) from exc


@router.get("", response_model=list[PluginStatusRead])
async def list_plugins(
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
) -> list[PluginStatusRead]:
    records = await plugin_service.list_plugins(db)
    return [PluginStatusRead.model_validate(r) for r in records]


@router.get("/{plugin_name}/status", response_model=PluginStatusRead)
async def get_plugin_status(
    plugin_name: str,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
) -> PluginStatusRead:
    try:
        record = await plugin_service.get_plugin_status(db, plugin_name)
        return PluginStatusRead.model_validate(record)
    except WikiError as exc:
        raise map_wiki_error(exc) from exc


@router.post("/{plugin_name}/enable", response_model=PluginStatusRead)
async def enable_plugin(
    plugin_name: str,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
) -> PluginStatusRead:
    try:
        record = await plugin_service.enable_plugin(db, plugin_name)
        return PluginStatusRead.model_validate(record)
    except WikiError as exc:
        raise map_wiki_error(exc) from exc


@router.post("/{plugin_name}/disable", response_model=PluginStatusRead)
async def disable_plugin(
    plugin_name: str,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
) -> PluginStatusRead:
    try:
        record = await plugin_service.disable_plugin(db, plugin_name)
        return PluginStatusRead.model_validate(record)
    except WikiError as exc:
        raise map_wiki_error(exc) from exc


@router.delete("/{plugin_name}", status_code=204)
async def remove_plugin(
    plugin_name: str,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
) -> None:
    try:
        await plugin_service.remove_plugin(db, plugin_name)
    except WikiError as exc:
        raise map_wiki_error(exc) from exc


@router.get("/{plugin_name}/capabilities", response_model=CapabilityRead)
async def list_plugin_capabilities(
    plugin_name: str,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
) -> CapabilityRead:
    try:
        caps = await plugin_service.get_plugin_capabilities(db, plugin_name)
        return CapabilityRead(plugin_name=plugin_name, capabilities=caps)
    except WikiError as exc:
        raise map_wiki_error(exc) from exc


events_router = APIRouter(prefix="/events", tags=["events"])


@events_router.post("/emit", status_code=202)
async def emit_event(
    body: EventEmit,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
) -> dict:
    try:
        await plugin_service.emit_event(db, body)
        return {"status": "accepted"}
    except WikiError as exc:
        raise map_wiki_error(exc) from exc
