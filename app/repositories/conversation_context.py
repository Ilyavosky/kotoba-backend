import json
from typing import Any, cast


class ConversationContextRepository:
    def __init__(self, redis_client: Any) -> None:
        self.redis = redis_client

    async def get_history(self, user_id: str, lesson_id: str) -> list[dict]:
        key = f"conv:{user_id}:{lesson_id}"
        data = await self.redis.get(key)
        if data is None:
            return []
        return cast(list[dict[Any, Any]], json.loads(data))

    async def append_turn(
        self, user_id: str, lesson_id: str, user_message: str, agent_response: str
    ) -> None:
        key = f"conv:{user_id}:{lesson_id}"
        history = await self.get_history(user_id, lesson_id)
        history.append({"user_message": user_message, "agent_response": agent_response})
        await self.redis.set(key, json.dumps(history), ex=86400)
