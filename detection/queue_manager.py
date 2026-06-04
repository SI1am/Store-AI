import logging
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class BillingQueueManager:
    def __init__(self, redis_client: Any, store_id: str):
        """
        Manages the checkout queue state in Redis.
        redis_client can be a sync/async Redis client or an in-memory mock.
        """
        self.redis = redis_client
        self.store_id = store_id
        self.queue_key = f"queue:{store_id}"
        self.depth_key = f"queue_depth:{store_id}"
        self.ttl = 86400  # 24 hours in seconds

    def is_async(self) -> bool:
        """Returns True if the Redis client is an asyncio-based asynchronous client."""
        # Simple heuristic to check if methods are coroutines
        return hasattr(self.redis, "rpush") and hasattr(getattr(self.redis, "rpush"), "__code__") and \
               ("async" in str(getattr(self.redis, "rpush")))

    async def person_enters_billing_zone(self, visitor_id: str, timestamp: datetime) -> Dict[str, Any]:
        """
        Registers a customer entering the checkout counter zone.
        Appends to the queue and returns metadata for event emission.
        """
        try:
            # Check if redis supports async calls
            if hasattr(self.redis, "rpush") and hasattr(self.redis, "pipeline"):
                # We assume async execution for Redis in the web layer, fallback to sync
                # Let's write it to handle both
                try:
                    # Async execution
                    await self.redis.rpush(self.queue_key, visitor_id)
                    await self.redis.incr(self.depth_key)
                    await self.redis.expire(self.queue_key, self.ttl)
                    await self.redis.expire(self.depth_key, 3600)  # 1 hour TTL for depth cache
                    queue_len = await self.redis.llen(self.queue_key)
                except (TypeError, AttributeError):
                    # Sync execution
                    self.redis.rpush(self.queue_key, visitor_id)
                    self.redis.incr(self.depth_key)
                    self.redis.expire(self.queue_key, self.ttl)
                    self.redis.expire(self.depth_key, 3600)
                    queue_len = self.redis.llen(self.queue_key)
            else:
                # Mock or local dict fallbacks if Redis is down
                queue_len = 1
                
            return {
                'queue_depth': queue_len,
                'position_in_queue': queue_len
            }
        except Exception as e:
            logger.warning(f"Redis queue join operation failed: {e}")
            return {'queue_depth': 1, 'position_in_queue': 1}

    async def person_exits_billing_zone(self, visitor_id: str, enter_time: datetime, exit_time: datetime) -> Optional[Dict[str, Any]]:
        """
        Registers a customer leaving the counter.
        - Removes them from the checkout queue.
        - If the counter dwell time is under 30 seconds, they abandoned checkout (emit event).
        - Otherwise, they successfully purchased (no event).
        """
        try:
            if hasattr(self.redis, "lpop"):
                try:
                    # Pop from the FIFO queue
                    await self.redis.lpop(self.queue_key)
                    await self.redis.decr(self.depth_key)
                    queue_len = await self.redis.llen(self.queue_key)
                except (TypeError, AttributeError):
                    self.redis.lpop(self.queue_key)
                    self.redis.decr(self.depth_key)
                    queue_len = self.redis.llen(self.queue_key)
            else:
                queue_len = 0

            dwell_sec = (exit_time - enter_time).total_seconds()
            
            # Checkout abandonment threshold: 30 seconds (30,000 milliseconds)
            if dwell_sec < 30.0:
                logger.info("billing_queue_abandoned", visitor=visitor_id, wait_sec=dwell_sec)
                return {
                    'queue_depth': queue_len,
                    'severity': 'ABANDONMENT',
                    'dwell_ms': int(dwell_sec * 1000)
                }
                
            logger.info("billing_queue_purchased", visitor=visitor_id, duration_sec=dwell_sec)
            return None
        except Exception as e:
            logger.warning(f"Redis queue exit operation failed: {e}")
            return None

    async def get_current_queue_depth(self) -> int:
        """Returns the current billing queue depth."""
        try:
            if hasattr(self.redis, "llen"):
                try:
                    return await self.redis.llen(self.queue_key)
                except (TypeError, AttributeError):
                    return self.redis.llen(self.queue_key)
            return 0
        except Exception as e:
            logger.warning(f"Failed to fetch queue depth: {e}")
            return 0
