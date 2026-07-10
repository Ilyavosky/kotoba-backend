import asyncio
from typing import Any

from supabase import Client

from app.schemas.telemetry import TelemetryEventIn


class TelemetryRepository:
    def __init__(self, client: Client) -> None:
        self._client = client

    async def insert_events(
        self, user_id: str, events: list[TelemetryEventIn]
    ) -> None:
        rows: list[dict[str, Any]] = [
            {
                "user_id": user_id,
                "event_type": event.event_type,
                "payload": event.payload,
                "occurred_at": event.occurred_at.isoformat(),
                "app_version": event.app_version,
                "platform": event.platform,
            }
            for event in events
        ]
        await asyncio.to_thread(
            lambda: self._client.table("telemetry_events")
            .insert(rows)
            .execute()
        )
