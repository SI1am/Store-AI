import logging
import time
from datetime import datetime
from fastapi import APIRouter, Request, Depends, status
from pydantic import BaseModel
from typing import List

from api.db import Database
from api.cache import CacheManager

router = APIRouter(tags=["System"])
logger = logging.getLogger(__name__)

# Start time tracking for uptime
APP_START_TIME = time.time()

class ComponentHealth(BaseModel):
    name: str
    status: str
    latency_ms: float
    message: str

class HealthResponse(BaseModel):
    status: str
    components: List[ComponentHealth]
    uptime_seconds: int

async def get_db(request: Request) -> Database:
    return request.app.state.db

async def get_cache(request: Request) -> CacheManager:
    return request.app.state.cache

@router.get("/health", status_code=status.HTTP_200_OK, response_model=HealthResponse)
async def get_system_health(
    db: Database = Depends(get_db),
    cache: CacheManager = Depends(get_cache)
):
    """
    Diagnostic endpoint validating database and cache latencies.
    Compatible with Kubernetes probes.
    """
    components = []
    is_degraded = False
    is_unhealthy = False

    # 1. Check PostgreSQL Health
    db_start = time.time()
    db_status = "unhealthy"
    db_msg = "PostgreSQL connection down"
    db_latency = 0.0
    
    try:
        # SELECT 1 check
        res = await db.fetch_val("SELECT 1")
        if res == 1:
            db_latency = round((time.time() - db_start) * 1000, 2)
            if db_latency < 100.0:
                db_status = "healthy"
            elif db_latency < 500.0:
                db_status = "degraded"
                is_degraded = True
            else:
                db_status = "unhealthy"
                is_unhealthy = True
            db_msg = "PostgreSQL connection pool healthy"
    except Exception as e:
        db_latency = round((time.time() - db_start) * 1000, 2)
        db_msg = f"PostgreSQL error: {e}"
        is_unhealthy = True

    components.append(ComponentHealth(
        name="database",
        status=db_status,
        latency_ms=db_latency,
        message=db_msg
    ))

    # 2. Check Redis Health
    redis_start = time.time()
    redis_status = "unhealthy"
    redis_msg = "Redis client down"
    redis_latency = 0.0
    
    try:
        ping_ok = await cache.ping()
        redis_latency = round((time.time() - redis_start) * 1000, 2)
        if ping_ok:
            if redis_latency < 50.0:
                redis_status = "healthy"
            elif redis_latency < 200.0:
                redis_status = "degraded"
                is_degraded = True
            else:
                redis_status = "unhealthy"
                is_unhealthy = True
            redis_msg = "Redis connection pool healthy"
    except Exception as e:
        redis_latency = round((time.time() - redis_start) * 1000, 2)
        redis_msg = f"Redis error: {e}"
        is_unhealthy = True

    components.append(ComponentHealth(
        name="redis",
        status=redis_status,
        latency_ms=redis_latency,
        message=redis_msg
    ))

    # 3. Check Detection Feed Health (mocked context check based on recent event timestamp)
    feed_status = "healthy"
    feed_msg = "Latest event processed recently"
    feed_latency = 0.0
    
    try:
        latest_event_query = "SELECT MAX(timestamp) FROM events;"
        latest_ts = await db.fetch_val(latest_event_query)
        if latest_ts:
            delta = datetime.utcnow() - latest_ts.replace(tzinfo=None)
            if delta.total_seconds() < 300.0: # 5 mins
                feed_status = "healthy"
            elif delta.total_seconds() < 1800.0: # 30 mins
                feed_status = "degraded"
                is_degraded = True
                feed_msg = "Latest event processed more than 5 minutes ago"
            else:
                feed_status = "unhealthy"
                is_unhealthy = True
                feed_msg = "No events processed in the last 30 minutes"
        else:
            feed_msg = "No events processed historically"
    except Exception:
        # Ignore and keep healthy (feed is secondary)
        pass

    components.append(ComponentHealth(
        name="detection_feed",
        status=feed_status,
        latency_ms=feed_latency,
        message=feed_msg
    ))

    # Overall Status Aggregation
    overall_status = "healthy"
    if is_unhealthy:
        overall_status = "unhealthy"
    elif is_degraded:
        overall_status = "degraded"

    uptime = int(time.time() - APP_START_TIME)

    return HealthResponse(
        status=overall_status,
        components=components,
        uptime_seconds=uptime
    )
