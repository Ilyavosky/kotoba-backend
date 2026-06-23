import json
from typing import cast

import redis.asyncio as aioredis

from app.schemas.domain import ConversationTurn


class ConversationContextRepository:
    def __init__(self, redis_client: aioredis.Redis) -> None:
        self.redis = redis_client

    async def get_history(self, user_id: str, lesson_id: str) -> list[ConversationTurn]:
        key = f"conv:{user_id}:{lesson_id}"
        items = await self.redis.lrange(key, 0, -1)
        return [cast(ConversationTurn, json.loads(item)) for item in items]

    async def append_turn(
        self, user_id: str, lesson_id: str, user_message: str, agent_response: str
    ) -> None:
        key = f"conv:{user_id}:{lesson_id}"
        pipe = self.redis.pipeline()
        pipe.rpush(key, json.dumps({"rol": "estudiante", "contenido": user_message}))
