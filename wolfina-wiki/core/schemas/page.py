from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from core.models.page import PageStatus, RelationType


class PageCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    slug: str = Field(..., min_length=1, max_length=512, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    content: str = ""
    summary: str = ""
    canonical_facts: list[Any] | dict[str, Any] | None = None
    source_refs: list[str] | None = None
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    creator_agent_id: str = Field(..., min_length=1)
    creation_reason: str = ""


class PageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    slug: str
    content: str
    summary: str
    canonical_facts: str | None
    source_refs: str | None
    confidence: float | None
    status: PageStatus
    created_at: datetime
    updated_at: datetime


class PageVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    page_id: str
    version_number: int
    title: str
    content: str
    summary: str
    editor_agent_id: str
    edit_reason: str
    proposal_id: str | None
    created_at: datetime


class RelationCreate(BaseModel):
    source_page_id: str
    target_page_id: str
    relation_type: RelationType
    created_by_agent: str = Field(..., min_length=1)


class RelationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_page_id: str
    target_page_id: str
    relation_type: RelationType
    created_at: datetime
    created_by_agent: str


class SortField(str, Enum):
    updated_at = "updated_at"
    created_at = "created_at"
    title = "title"


class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


class PageSearchParams(BaseModel):
    q: str = ""
    status: PageStatus | None = None
    updated_after: datetime | None = None
    sort_by: SortField = SortField.updated_at
    sort_order: SortOrder = SortOrder.desc
    limit: int = Field(20, ge=1, le=200)
    offset: int = Field(0, ge=0)
