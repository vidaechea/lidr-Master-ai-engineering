"""Event schemas for turn observation and analytics."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class CacheHitKind(str, Enum):
    """Type of cache hit achieved for this turn."""

    NONE = "none"
    EXACT = "exact"
    SEMANTIC = "semantic"


class TurnObservedEvent(BaseModel):
    """Unified observation event emitted at the end of each estimation turn.

    Consolidates all relevant metrics from a single turn: cache status,
    token usage, cost, latency, and conversation context.
    """

    turn_index: int = Field(
        description="1-based turn counter within the session"
    )
    session_id: str = Field(
        description="Unique session identifier"
    )
    enriched_transcript_chars: int = Field(
        description="Character count of transcription + concatenated attachments"
    )
    attachments_total_chars: int = Field(
        ge=0,
        description="Total character count from all uploaded attachments (0 if none)"
    )
    messages_in_window: int = Field(
        ge=1,
        description="Number of messages in history after compression"
    )
    anchors_count: int = Field(
        ge=0,
        description="Number of key information anchors extracted"
    )
    summary_chars: int = Field(
        ge=0,
        description="Character count of the conversation summary"
    )
    tokens_in: int = Field(
        ge=1,
        description="Input tokens consumed by the LLM"
    )
    tokens_out: int = Field(
        ge=1,
        description="Output tokens produced by the LLM"
    )
    cost_usd: float = Field(
        ge=0.0,
        description="USD cost of this turn's LLM call"
    )
    latency_ms: float = Field(
        ge=0.0,
        description="Elapsed time in milliseconds for the estimation call"
    )
    cache_hit_kind: CacheHitKind = Field(
        default=CacheHitKind.NONE,
        description="Type of cache hit (exact, semantic, or none)"
    )
    last_resolved_tier: Optional[str] = Field(
        default=None,
        description="User tier resolved by the estimation logic, if any"
    )
    model: str = Field(
        description="LLM model name used for this turn"
    )
    response_id: str = Field(
        description="Unique identifier for the LLM response"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "turn_index": 1,
                "session_id": "sess_abc123",
                "enriched_transcript_chars": 5240,
                "attachments_total_chars": 1200,
                "messages_in_window": 3,
                "anchors_count": 2,
                "summary_chars": 450,
                "tokens_in": 1240,
                "tokens_out": 320,
                "cost_usd": 0.0025,
                "latency_ms": 2500.5,
                "cache_hit_kind": "none",
                "last_resolved_tier": "premium",
                "model": "gpt-4",
                "response_id": "resp_xyz789",
            }
        }
