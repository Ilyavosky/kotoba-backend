import asyncio
import json
from datetime import UTC, datetime
from typing import Any, cast

import redis.asyncio as aioredis
import structlog
from supabase import Client

from app.schemas.student_model import StudentModel

logger = structlog.get_logger(__name__)

# 24-hour TTL, matches conversation history and step state expiry
_TTL = 86400


class StudentModelRepository:
    """Dual persistence for the student model (K-06.1).

    Redis is the hot, per-session copy (key 'student:{user_id}:{lesson_id}');
    Supabase 'student_models' is the durable mirror. Reads fall back from
    Redis to Supabase and rehydrate Redis on the way back, so a session can
    resume seamlessly after the TTL expires.
    """

    def __init__(self, redis_client: aioredis.Redis, supabase_client: Client) -> None:
        self.redis = redis_client
        self._client = supabase_client

    @staticmethod
    def _key(user_id: str, lesson_id: str) -> str:
        return f"student:{user_id}:{lesson_id}"

    async def get_model(self, user_id: str, lesson_id: str) -> StudentModel | None:
        try:
            raw = await self.redis.get(self._key(user_id, lesson_id))
            if raw is not None:
                return cast(StudentModel, json.loads(raw))
        except Exception as e:
            logger.warning("student_model_redis_get_failed", error=str(e))
        result = await asyncio.to_thread(
            lambda: self._client.table("student_models")
            .select("vocabulary, error_patterns, bkt, session_turns")
            .eq("user_id", user_id)
            .eq("lesson_id", lesson_id)
            .execute()
        )
        if not result.data:
            return None

        row = cast(dict[str, Any], result.data[0])
        model = StudentModel(
            vocabulary=row["vocabulary"],
            error_patterns=row["error_patterns"],
            bkt=row["bkt"],
            session_turns=int(row["session_turns"]),
        )
        try:
            await self.redis.set(
                self._key(user_id, lesson_id), json.dumps(model), ex=_TTL
            )
        except Exception as e:
            logger.warning("student_model_rehydrate_failed", error=str(e))

        return model

    async def save_model(
        self, user_id: str, lesson_id: str, model: StudentModel
    ) -> None:
        try:
            await self.redis.set(
                self._key(user_id, lesson_id), json.dumps(model), ex=_TTL
            )
        except Exception as e:
            logger.warning("student_model_redis_save_failed", error=str(e))

        payload: dict[str, Any] = {
            "user_id": user_id,
            "lesson_id": lesson_id,
            "vocabulary": model["vocabulary"],
            "error_patterns": model["error_patterns"],
            "bkt": model["bkt"],
            "session_turns": model["session_turns"],
            "updated_at": datetime.now(UTC).isoformat(),
        }
        await asyncio.to_thread(
            lambda: self._client.table("student_models")
            .upsert(payload, on_conflict="user_id,lesson_id")
            .execute()
        )
