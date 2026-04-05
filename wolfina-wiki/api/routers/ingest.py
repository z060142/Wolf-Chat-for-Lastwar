"""Ingest endpoint — receives conversation messages from external sources (e.g. wolf-chat).

POST /ingest
  Body: {"speaker": "PlayerName", "content": "message text", "timestamp": "2026-01-01T12:00:00Z"}
  No auth required (internal use only).
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from core.conversation_buffer import conversation_buffer

router = APIRouter(prefix="/ingest", tags=["ingest"])


class IngestMessage(BaseModel):
    speaker: str
    content: str
    timestamp: Optional[datetime] = None


class IngestResponse(BaseModel):
    message_id: str
    pending_count: int
    should_trigger: bool


@router.post("", response_model=IngestResponse)
async def ingest_message(payload: IngestMessage) -> IngestResponse:
    msg = conversation_buffer.add_message(
        speaker=payload.speaker,
        content=payload.content,
        timestamp=payload.timestamp,
    )
    stats = conversation_buffer.get_stats()
    return IngestResponse(
        message_id=msg.id,
        pending_count=stats["pending_count"],
        should_trigger=conversation_buffer.should_trigger(),
    )
