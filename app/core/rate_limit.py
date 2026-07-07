import time
from collections.abc import Awaitable
from typing import cast

import redis.asyncio as aioredis
import structlog
from fastapi import HTTPException, status


class RateLimiter:
    def __init__(self, redis_client: aioredis.Redis, limit_per_minute: int) -> None:
        self._redis = redis_client
        self._limit = limit_per_minute

    async def check(self, user_id: str) -> None:
        window = int(time.time() // 60)
        key = f"rl:turn:{user_id}:{window}"
        try:
            count = await cast("Awaitable[int]", self._redis.incr(key))
            if count == 1:
                await cast("Awaitable[bool]", self._redis.expire(key, 120))
        except Exception as e:
            structlog.get_logger().warning(
                "rate_limit_redis_unavailable", error=str(e)
            )
            return
        if count > self._limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests, please slow down",
            )
