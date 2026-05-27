from contextlib import asynccontextmanager

import redis.asyncio as redis

from app.core.config import settings

redis_client = redis.from_url(url=settings.UPSTASH_REDIS_URL)


@asynccontextmanager
async def lifespan(app):
    yield
    await redis_client.aclose()
