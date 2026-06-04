import logging
import json
import redis.asyncio as aioredis
from typing import Optional, Any

logger = logging.getLogger(__name__)

class CacheManager:
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.client: Optional[aioredis.Redis] = None

    async def connect(self) -> None:
        """Initializes the asynchronous Redis connection client."""
        if self.client is not None:
            return
            
        logger.info("Connecting to Redis AsyncIO client...")
        try:
            self.client = aioredis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_timeout=5.0
            )
            await self.client.ping()
            logger.info("Redis AsyncIO connection verified successfully.")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis (Cache degraded mode): {e}")
            self.client = None

    async def disconnect(self) -> None:
        """Closes the Redis connection client."""
        if self.client is None:
            return
            
        logger.info("Closing Redis connection...")
        try:
            await self.client.close()
            self.client = None
            logger.info("Redis connection closed cleanly.")
        except Exception as e:
            logger.warning(f"Failed to close Redis connection: {e}")

    async def get(self, key: str) -> Optional[str]:
        """Gets a string value from the cache. Degrades gracefully to None on failure."""
        if self.client is None:
            return None
        try:
            return await self.client.get(key)
        except Exception as e:
            logger.warning(f"Redis get failed for key '{key}': {e}")
            return None

    async def set(self, key: str, value: str, ttl: int = 300) -> None:
        """Sets a string value in the cache with a specified TTL (in seconds). Degrades gracefully."""
        if self.client is None:
            return
        try:
            await self.client.set(key, value, ex=ttl)
        except Exception as e:
            logger.warning(f"Redis set failed for key '{key}': {e}")

    async def delete(self, key: str) -> None:
        """Deletes a key from the cache. Degrades gracefully."""
        if self.client is None:
            return
        try:
            await self.client.delete(key)
        except Exception as e:
            logger.warning(f"Redis delete failed for key '{key}': {e}")

    async def sismember(self, key: str, member: str) -> bool:
        """Checks if a member exists in a Redis set. Defaults to False on failure."""
        if self.client is None:
            return False
        try:
            return bool(await self.client.sismember(key, member))
        except Exception as e:
            logger.warning(f"Redis sismember check failed for set '{key}': {e}")
            return False

    async def sadd(self, key: str, member: str) -> None:
        """Adds a member to a Redis set and sets a 24-hour TTL default. Degrades gracefully."""
        if self.client is None:
            return
        try:
            await self.client.sadd(key, member)
            await self.client.expire(key, 86400)  # 24 hour TTL for set persistence
        except Exception as e:
            logger.warning(f"Redis sadd failed for set '{key}': {e}")

    async def rpush(self, key: str, value: str) -> None:
        """Appends a value to the tail of a Redis list queue. Degrades gracefully."""
        if self.client is None:
            return
        try:
            await self.client.rpush(key, value)
            await self.client.expire(key, 86400)
        except Exception as e:
            logger.warning(f"Redis rpush failed for list '{key}': {e}")

    async def lpop(self, key: str) -> Optional[str]:
        """Pops and returns the first value from a Redis list queue. Degrades gracefully."""
        if self.client is None:
            return None
        try:
            return await self.client.lpop(key)
        except Exception as e:
            logger.warning(f"Redis lpop failed for list '{key}': {e}")
            return None

    async def llen(self, key: str) -> int:
        """Returns the length of a Redis list queue. Defaults to 0 on failure."""
        if self.client is None:
            return 0
        try:
            return int(await self.client.llen(key))
        except Exception as e:
            logger.warning(f"Redis llen failed for list '{key}': {e}")
            return 0

    async def ping(self) -> bool:
        """Pings the Redis server to verify connectivity. Returns False on failure."""
        if self.client is None:
            return False
        try:
            await self.client.ping()
            return True
        except Exception as e:
            logger.warning(f"Redis ping failed: {e}")
            return False
