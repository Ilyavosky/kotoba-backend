from __future__ import annotations
import redis.asyncio as redis
from app.core.config import settings
from contextlib import asynccontextmanager


redis_client = redis.from_url(url= settings.UPSTASH_REDIS_URL)

@asynccontextmanager
async def lifespan(app: FastAPI):
    
    yield
    await redis_client.aclose()