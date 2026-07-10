from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class TelemetryEventIn(BaseModel):
    """A single client-side event, as sent by the mobile app."""

    event_type: str = Field(min_length=1, max_length=100)
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
    app_version: str | None = Field(default=None, max_length=20)
    platform: Literal["android", "ios", "web"] | None = None


class TelemetryBatchIn(BaseModel):
    events: list[TelemetryEventIn] = Field(min_length=1)


class TelemetryIngestResponse(BaseModel):
    accepted: int
