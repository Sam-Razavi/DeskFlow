"""Failure counters in Redis, used to slow down password guessing.

Each key holds a count that expires on its own, so there is nothing to clean up. If Redis cannot
be reached the limiter lets requests through ("fails open"): a cache outage should not stop every
user from signing in.
"""

import logging
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

logger = logging.getLogger("deskflow.ratelimit")


class RateLimiter:
    def __init__(self, url: str) -> None:
        # Short timeouts: this sits on the sign-in path, so it must not hang when Redis is down.
        self._redis: Redis = Redis.from_url(
            url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1
        )

    async def state(self, key: str) -> tuple[int, int]:
        """The current failure count and the seconds until it expires, or (0, 0)."""
        try:
            async with self._redis.pipeline(transaction=False) as pipe:
                pipe.get(key)
                pipe.ttl(key)
                count, ttl = await pipe.execute()
        except (RedisError, OSError):
            logger.warning("Rate limiter unavailable; allowing the request", exc_info=True)
            return 0, 0
        return int(count or 0), max(int(ttl), 0)

    async def record(self, key: str, window_seconds: int) -> None:
        """Count one more failure, starting the expiry clock with the first."""
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                pipe.expire(key, window_seconds, nx=True)  # only when the key has no expiry yet
                await pipe.execute()
        except (RedisError, OSError):
            logger.warning("Rate limiter unavailable; failure not recorded", exc_info=True)

    async def reset(self, key: str) -> None:
        try:
            await self._redis.delete(key)
        except (RedisError, OSError):
            logger.warning("Rate limiter unavailable; counter not reset", exc_info=True)


@lru_cache
def get_limiter() -> RateLimiter:
    return RateLimiter(get_settings().redis_url)


LimiterDep = Annotated[RateLimiter, Depends(get_limiter)]
