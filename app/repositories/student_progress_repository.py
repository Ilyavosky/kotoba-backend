import asyncio
from datetime import UTC, datetime
from typing import Any, Literal, cast

from supabase import Client


class StudentProgressRepository:
    def __init__(self, client: Client) -> None:
        self._client = client

    async def get_progress(
                        self,
                        user_id: str,
                        lesson_id: str
                        ) -> dict[str, Any] | None:

        raw = await asyncio.to_thread(
            lambda: self._client.table("user_progress")
            .select("current_step, status")
            .eq("user_id", user_id)
            .eq("lesson_id", lesson_id)
            .execute()
        )
        if not raw.data:
            return None
        return cast(dict[str, Any], raw.data[0])

    async def upsert_progress(
                        self,
                        user_id: str,
                        lesson_id: str,
                        current_step: int,
                        status: Literal["not_started", "in_progress", "completed"],
                        ) -> None:
        payload: dict[str, Any] = {
                    "user_id": user_id,
                    "lesson_id": lesson_id,
                    "current_step": current_step,
                    "status": status,
                    "updated_at": datetime.now(UTC).isoformat(),
                    }
        await asyncio.to_thread(
            lambda: self._client.table("user_progress")
            .upsert(payload, on_conflict="user_id,lesson_id")
            .execute()
        )
