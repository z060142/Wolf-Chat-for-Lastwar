"""Non-blocking, fire-and-forget event bus.

Handlers are scheduled as independent asyncio tasks so that:
  - A slow or crashing handler never blocks the caller.
  - Core request processing is never delayed by plugin side-effects.
"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable

from core.events.event_types import Event

logger = logging.getLogger(__name__)

Handler = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Handler) -> None:
        """Register a coroutine handler for the given event type.

        Use ``"*"`` to subscribe to every event.
        """
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Handler) -> None:
        try:
            self._handlers[event_type].remove(handler)
        except ValueError:
            pass

    def emit(self, event: Event) -> None:
        """Schedule delivery of *event* to all matching handlers.

        Delivery is fire-and-forget: the caller is never awaited.
        Each handler runs in its own task; failures are logged and swallowed.
        """
        handlers = list(self._handlers.get(event.type, []))
        handlers += list(self._handlers.get("*", []))
        for handler in handlers:
            asyncio.ensure_future(self._safe_call(handler, event))

    @staticmethod
    async def _safe_call(handler: Handler, event: Event) -> None:
        try:
            await handler(event)
        except Exception:
            logger.exception(
                "Plugin event handler %s raised an unhandled exception for event %s",
                getattr(handler, "__qualname__", repr(handler)),
                event.type,
            )


# Module-level singleton shared across the application.
event_bus = EventBus()
