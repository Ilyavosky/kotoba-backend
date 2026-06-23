import json
from typing import cast

import redis.asyncio as aioredis

from app.schemas.domain import StepState

#exp of 24hrs as conversation_context.py
_TTL = 86400

class StepStateRepository:
    def __init__(self, redis_client: aioredis.Redis[bytes]) -> None:
        self.redis = redis_client

    async def get_step_state(self, user_id: str, lesson_id: str) -> StepState | None:
        key = f"step:{user_id}:{lesson_id}"
        items = await self.redis.get(key)
        if items is None: return None
        return cast(StepState, json.loads(items))
    
    async def save_step_state(self, user_id: str, lesson_id: str, state: StepState) -> None:
        key = f"step:{user_id}:{lesson_id}"
        await self.redis.set(key, json.dumps(state), ex=_TTL) 