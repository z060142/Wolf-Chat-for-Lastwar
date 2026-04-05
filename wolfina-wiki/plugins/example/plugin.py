"""Example plugin: logs page_created and proposal_applied events.

This demonstrates how to build a conformant plugin without coupling to core internals.
It is intentionally minimal.
"""

import logging

from core.events.event_bus import EventBus
from core.events.event_types import Event, EventType
from plugins.base_plugin import BasePlugin

logger = logging.getLogger(__name__)


class ExamplePlugin(BasePlugin):
    @property
    def name(self) -> str:
        return "example"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def capabilities(self) -> list[str]:
        return ["observe:page_created", "observe:proposal_applied"]

    async def on_load(self, event_bus: EventBus) -> None:
        self._bus = event_bus
        event_bus.subscribe(EventType.page_created, self._handle_page_created)
        event_bus.subscribe(EventType.proposal_applied, self._handle_proposal_applied)
        logger.info("[ExamplePlugin] Loaded and subscribed to events.")

    async def on_unload(self) -> None:
        self._bus.unsubscribe(EventType.page_created, self._handle_page_created)
        self._bus.unsubscribe(EventType.proposal_applied, self._handle_proposal_applied)
        logger.info("[ExamplePlugin] Unloaded.")

    async def _handle_page_created(self, event: Event) -> None:
        logger.info("[ExamplePlugin] New page created: %s", event.payload.get("page_id"))

    async def _handle_proposal_applied(self, event: Event) -> None:
        logger.info(
            "[ExamplePlugin] Proposal %s applied to page %s by executor %s",
            event.payload.get("proposal_id"),
            event.payload.get("page_id"),
            event.payload.get("executor"),
        )
