from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI

from app.core.config import settings

redis_client: aioredis.Redis = aioredis.from_url(url=settings.UPSTASH_REDIS_URL)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    yield
    await redis_client.aclose()
