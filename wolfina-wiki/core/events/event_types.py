from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    page_created = "page_created"
    page_updated = "page_updated"
    page_archived = "page_archived"
    proposal_created = "proposal_created"
    proposal_reviewed = "proposal_reviewed"
    proposal_applied = "proposal_applied"
    relation_added = "relation_added"
    plugin_enabled = "plugin_enabled"
    plugin_disabled = "plugin_disabled"
    # Allows plugins to emit arbitrary typed events.
    custom = "custom"


@dataclass
class Event:
    type: EventType | str
    payload: dict[str, Any] = field(default_factory=dict)
    source_plugin: str | None = None
