from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as redis

from app.core.config import settings

redis_client = redis.from_url(url=settings.UPSTASH_REDIS_URL)


@asynccontextmanager
async def lifespan(app: Any) -> AsyncGenerator[None, None]:
    yield
    await redis_client.aclose()
