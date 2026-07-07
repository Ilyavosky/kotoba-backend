import json
from collections.abc import Awaitable
from typing import cast

import redis.asyncio as aioredis

from app.schemas.domain import ConversationTurn

# 24-hour TTL, matches step state expiry (step_state_repository._TTL)
_TTL = 86400


class ConversationContextRepository:
    def __init__(self, redis_client: aioredis.Redis) -> None:
        self.redis = redis_client

    async def get_history(self, user_id: str, lesson_id: str) -> list[ConversationTurn]:
        key = f"conv:{user_id}:{lesson_id}"
        items = await cast(
            "Awaitable[list[str]]", self.redis.lrange(key, 0, -1)
        )
        return [cast(ConversationTurn, json.loads(item)) for item in items]

    async def append_turn(
        self, user_id: str, lesson_id: str, user_message: str, agent_response: str
    ) -> None:
        key = f"conv:{user_id}:{lesson_id}"
        pipe = self.redis.pipeline()
        pipe.rpush(
            key,
            json.dumps(
                {"rol": "estudiante", "contenido": user_message}, ensure_ascii=False
            ),
        )
        pipe.rpush(
            key,
            json.dumps(
                {"rol": "agente", "contenido": agent_response}, ensure_ascii=False
            ),
        )
        pipe.expire(key, _TTL)
        await pipe.execute()
