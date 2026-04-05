"""Abstract base class for Wolfina Wiki plugins.

Concrete plugins subclass BasePlugin and are loaded by the plugin registry.
The core system only imports BasePlugin — never concrete implementations.
This ensures that removing or failing to import a plugin cannot affect core functionality.
"""

from abc import ABC, abstractmethod

from core.events.event_bus import EventBus


class BasePlugin(ABC):
    """Contract every plugin must fulfil."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique machine-readable identifier, e.g. ``"my-plugin"``."""

    @property
    @abstractmethod
    def version(self) -> str:
        """SemVer string, e.g. ``"1.0.0"``."""

    @property
    def capabilities(self) -> list[str]:
        """List of capability tokens declared by this plugin.

        Examples: ``["read:pages", "emit:events", "propose:edits"]``
        """
        return []

    @abstractmethod
    async def on_load(self, event_bus: EventBus) -> None:
        """Called when the plugin is registered/enabled.

        Subscribe to events here via ``event_bus.subscribe(event_type, handler)``.
        """

    @abstractmethod
    async def on_unload(self) -> None:
        """Called when the plugin is disabled/removed.

        Unsubscribe handlers and release resources here.
        """
