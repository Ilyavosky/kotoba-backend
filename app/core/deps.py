from groq import Groq

from app.core.redis import redis_client
from app.repositories.conversation_context import ConversationContextRepository


def get_groq_client() -> Groq:
    return Groq()

async def get_redis_repository():
    repository =ConversationContextRepository(redis_client)
    return repository
