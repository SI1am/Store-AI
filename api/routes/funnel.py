import logging
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, Depends, HTTPException, status
from pydantic import BaseModel

from api.db import Database
from api.cache import CacheManager

router = APIRouter(tags=["Analytics"])
logger = logging.getLogger(__name__)

class FunnelStage(BaseModel):
    stage: str
    count: int
    conversion_percent: float
    dropoff_percent: float

async def get_db(request: Request) -> Database:
    return request.app.state.db

async def get_cache(request: Request) -> CacheManager:
    return request.app.state.cache

@router.get("/stores/{store_id}/funnel")
async def get_conversion_funnel(
    store_id: str,
    date: Optional[str] = None,
    include_staff: bool = False,
    db: Database = Depends(get_db),
    cache: CacheManager = Depends(get_cache)
):
    """
    Computes a 4-stage shopper conversion funnel:
    Entry -> Zone Visit -> Billing Queue -> Purchase.
    Uses distinct shopper IDs to prevent double-counting.
    """
    query_date_str = date or datetime.utcnow().strftime("%Y-%m-%d")
    try:
        query_date = datetime.strptime(query_date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Date must be YYYY-MM-DD format."
        )

    # 1. Check Cache
    cache_key = f"funnel:{store_id}:{query_date_str}:{include_staff}"
    cached_data = await cache.get(cache_key)
    if cached_data:
        try:
            parsed_data = json.loads(cached_data)
            return {
                "status": "ok",
                "data": parsed_data,
                "meta": {
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    "trace_id": "CACHED",
                    "cached": True
                }
            }
        except Exception:
            logger.warning("failed_to_parse_cached_funnel")

    # 2. Database Queries
    staff_filter = "" if include_staff else "AND is_staff = FALSE"
    e_staff_filter = "" if include_staff else "AND e.is_staff = FALSE"

    # Stage 1: Store Entries
    entry_query = f"""
        SELECT COUNT(DISTINCT visitor_id) FROM events
        WHERE store_id = $1 AND event_type = 'ENTRY' {staff_filter} AND DATE(timestamp) = $2;
    """
    entry_count = await db.fetch_val(entry_query, store_id, query_date) or 0

    # Stage 2: Department Visits (exclude billing queue counter)
    visit_query = f"""
        SELECT COUNT(DISTINCT visitor_id) FROM events
        WHERE store_id = $1 AND event_type = 'ZONE_ENTER' AND zone_id != 'BILLING' {staff_filter} AND DATE(timestamp) = $2;
    """
    visit_count = await db.fetch_val(visit_query, store_id, query_date) or 0

    # Stage 3: Billing Queue Entrants
    queue_query = f"""
        SELECT COUNT(DISTINCT visitor_id) FROM events
        WHERE store_id = $1 AND event_type = 'BILLING_QUEUE_JOIN' {staff_filter} AND DATE(timestamp) = $2;
    """
    queue_count = await db.fetch_val(queue_query, store_id, query_date) or 0

    # Stage 4: Checkout Purchases (POS correlated)
    purchase_query = f"""
        WITH converted_visitors AS (
            SELECT DISTINCT e.visitor_id
            FROM events e
            INNER JOIN pos_transactions p ON e.store_id = p.store_id
            WHERE e.store_id = $1
              AND e.event_type = 'BILLING_QUEUE_JOIN'
              {e_staff_filter}
              AND DATE(p.timestamp) = $2
              AND e.timestamp BETWEEN (p.timestamp - INTERVAL '5 minutes') AND p.timestamp
        )
        SELECT COUNT(*) FROM converted_visitors;
    """
    purchase_count = await db.fetch_val(purchase_query, store_id, query_date) or 0

    # 3. Calculate Funnel conversion rates
    stages = []
    counts = [entry_count, visit_count, queue_count, purchase_count]
    stage_names = ["Entry", "Zone Visit", "Billing Queue", "Purchase"]

    for idx, (name, count) in enumerate(zip(stage_names, counts)):
        # Conversion is relative to first stage (Entry)
        conv = round((count / entry_count) * 100.0, 2) if entry_count > 0 else 0.0
        drop = round(100.0 - conv, 2) if entry_count > 0 else 0.0
        
        stages.append({
            "stage": name,
            "count": count,
            "conversion_percent": conv,
            "dropoff_percent": drop
        })

    total_conv = round(purchase_count / entry_count, 4) if entry_count > 0 else 0.0

    payload = {
        "store_id": store_id,
        "date": query_date_str,
        "stages": stages,
        "total_conversion_rate": total_conv
    }

    # 4. Save Cache (60s TTL)
    await cache.set(cache_key, json.dumps(payload), ttl=60)

    return {
        "status": "ok",
        "data": payload,
        "meta": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "trace_id": "LIVE",
            "cached": False
        }
    }
