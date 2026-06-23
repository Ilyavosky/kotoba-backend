import asyncio
import json
from typing import cast

from fastapi import HTTPException
from supabase import Client


class LessonRepository:
    def __init__(self, client: Client, bucket: str) -> None:
        self._client = client
        self._bucket = bucket
        self._cache: dict[str, dict[str, object]] = {}

    async def get_lesson(self, lesson_id: str) -> dict[str, object]:
        if lesson_id in self._cache:
            return self._cache[lesson_id]

        try:
            raw = await asyncio.to_thread(
                self._client.storage.from_(self._bucket).download,
                f"{lesson_id}.json",
            )
        except Exception as e:
            raise HTTPException(
                status_code=404, detail=f"Lesson '{lesson_id}' not found"
            ) from e

        lesson = cast(dict[str, object], json.loads(raw.decode("utf-8")))
        self._cache[lesson_id] = lesson
        return lesson
