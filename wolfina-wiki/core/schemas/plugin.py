from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PluginRegister(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-z0-9_-]+$")
    display_name: str = Field(..., min_length=1, max_length=256)
    description: str = ""
    version: str = Field(..., min_length=1, max_length=64)
    capabilities: list[str] = []


class PluginStatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    display_name: str
    description: str
    version: str
    capabilities: str  # raw JSON string; decoded by client
    enabled: bool
    registered_at: datetime
    updated_at: datetime


class EventEmit(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=128)
    payload: dict[str, Any] = {}
    source_plugin: str | None = None


class CapabilityRead(BaseModel):
    plugin_name: str
    capabilities: list[str]
