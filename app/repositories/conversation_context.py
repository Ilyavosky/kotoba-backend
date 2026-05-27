import json
import redis.asyncio as redis

class ConversationContextRepository:
    def __init__(self, redis_client):
        self.redis = redis_client
        
    async def get_history(self, user_id, lesson_id):
        key = f"conv:{user_id}:{lesson_id}"
        data = await self.redis.get(key)
        if data == None:
            return []
        return json.loads(data)
    
    async def append_turn(self, user_id, lesson_id, user_message, agent_response):
        key = f"conv:{user_id}:{lesson_id}"
        history = await self.get_history(user_id, lesson_id)
        history.append({
            "user_message": user_message,
            "agent_response": agent_response
        })
        await self.redis.set(key, json.dumps(history), ex=86400)