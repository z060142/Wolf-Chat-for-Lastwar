"""Plugin lifecycle management."""

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.events.event_bus import event_bus
from core.events.event_types import Event, EventType
from core.exceptions import Conflict, NotFound, PluginError
from core.models.plugin import PluginEventLog, PluginRecord
from core.schemas.plugin import EventEmit, PluginRegister

logger = logging.getLogger(__name__)


async def register_plugin(db: AsyncSession, data: PluginRegister) -> PluginRecord:
    existing = await db.scalar(select(PluginRecord).where(PluginRecord.name == data.name))
    if existing:
        raise Conflict(f"Plugin '{data.name}' is already registered. Use update instead.")

    record = PluginRecord(
        name=data.name,
        display_name=data.display_name,
        description=data.description,
        version=data.version,
        capabilities=json.dumps(data.capabilities),
        enabled=False,
    )
    db.add(record)
    await db.flush()
    logger.info("Plugin registered: %s v%s", data.name, data.version)
    return record


async def enable_plugin(db: AsyncSession, plugin_name: str) -> PluginRecord:
    record = await _get_record(db, plugin_name)
    if record.enabled:
        return record
    record.enabled = True
    await db.flush()
    event_bus.emit(Event(type=EventType.plugin_enabled, payload={"plugin": plugin_name}))
    logger.info("Plugin enabled: %s", plugin_name)
    return record


async def disable_plugin(db: AsyncSession, plugin_name: str) -> PluginRecord:
    record = await _get_record(db, plugin_name)
    if not record.enabled:
        return record
    record.enabled = False
    await db.flush()
    event_bus.emit(Event(type=EventType.plugin_disabled, payload={"plugin": plugin_name}))
    logger.info("Plugin disabled: %s", plugin_name)
    return record


async def remove_plugin(db: AsyncSession, plugin_name: str) -> None:
    record = await _get_record(db, plugin_name)
    await db.delete(record)
    await db.flush()
    logger.info("Plugin removed: %s", plugin_name)


async def get_plugin_status(db: AsyncSession, plugin_name: str) -> PluginRecord:
    return await _get_record(db, plugin_name)


async def list_plugins(db: AsyncSession) -> list[PluginRecord]:
    result = await db.scalars(select(PluginRecord).order_by(PluginRecord.name))
    return list(result.all())


async def emit_event(db: AsyncSession, data: EventEmit) -> None:
    """Accept an external event from a plugin and fan it out via the event bus.

    The event is logged regardless of delivery outcome; delivery failures are
    isolated and never propagate back to the caller.
    """
    if data.source_plugin:
        record = await db.scalar(select(PluginRecord).where(PluginRecord.name == data.source_plugin))
        if record and not record.enabled:
            raise PluginError(f"Plugin '{data.source_plugin}' is disabled and cannot emit events.")

    log_entry = PluginEventLog(
        plugin_id=data.source_plugin,
        event_type=data.event_type,
        payload=json.dumps(data.payload),
        source=data.source_plugin,
        status="emitted",
    )
    db.add(log_entry)
    await db.flush()

    event_bus.emit(
        Event(
            type=data.event_type,
            payload=data.payload,
            source_plugin=data.source_plugin,
        )
    )


async def get_plugin_capabilities(db: AsyncSession, plugin_name: str) -> list[str]:
    record = await _get_record(db, plugin_name)
    try:
        return json.loads(record.capabilities)
    except (json.JSONDecodeError, TypeError):
        return []


async def _get_record(db: AsyncSession, plugin_name: str) -> PluginRecord:
    record = await db.scalar(select(PluginRecord).where(PluginRecord.name == plugin_name))
    if record is None:
        raise NotFound(f"Plugin '{plugin_name}' not found.")
    return record
