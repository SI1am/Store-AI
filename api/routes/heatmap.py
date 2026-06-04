import logging
import json
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Request, Depends, HTTPException, status

from api.db import Database
from api.cache import CacheManager

router = APIRouter(tags=["Analytics"])
logger = logging.getLogger(__name__)

async def get_db(request: Request) -> Database:
    return request.app.state.db

async def get_cache(request: Request) -> CacheManager:
    return request.app.state.cache

@router.get("/stores/{store_id}/heatmap")
async def get_zone_heatmap(
    store_id: str,
    date: Optional[str] = None,
    include_staff: bool = False,
    db: Database = Depends(get_db),
    cache: CacheManager = Depends(get_cache)
):
    """
    Computes shopper engagement dwell durations across departments.
    Results are sorted by average engagement duration descending.
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
    cache_key = f"heatmap:{store_id}:{query_date_str}:{include_staff}"
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
            logger.warning("failed_to_parse_cached_heatmap")

    # 2. Database query: aggregate dwell durations per department zone
    # exit events (ZONE_EXIT and BILLING_QUEUE_ABANDON) hold calculated dwell times
    staff_filter = "" if include_staff else "AND is_staff = FALSE"
    heatmap_query = f"""
        SELECT 
            zone_id,
            COUNT(DISTINCT visitor_id) as total_entries,
            AVG(dwell_ms) as avg_dwell,
            MAX(dwell_ms) as max_dwell,
            MIN(dwell_ms) as min_dwell,
            STDDEV_POP(dwell_ms) as stddev_dwell
        FROM events
        WHERE store_id = $1 
          AND event_type IN ('ZONE_EXIT', 'BILLING_QUEUE_ABANDON') 
          {staff_filter} 
          AND DATE(timestamp) = $2
          AND zone_id IS NOT NULL
        GROUP BY zone_id
        ORDER BY avg_dwell DESC;
    """
    
    try:
        records = await db.fetch_all(heatmap_query, store_id, query_date)
        zones_data = []
        
        for r in records:
            zones_data.append({
                "zone_id": r["zone_id"],
                "total_entries": int(r["total_entries"]),
                "avg_dwell_ms": round(float(r["avg_dwell"]), 2) if r["avg_dwell"] else 0.0,
                "max_dwell_ms": int(r["max_dwell"]) if r["max_dwell"] else 0,
                "min_dwell_ms": int(r["min_dwell"]) if r["min_dwell"] else 0,
                "std_dev_dwell": round(float(r["stddev_dwell"]), 2) if r["stddev_dwell"] else 0.0
            })
            
        payload = {
            "store_id": store_id,
            "date": query_date_str,
            "zones": zones_data
        }
        
        # 3. Save Cache (60s TTL)
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
    except Exception as e:
        error_msg = f"Failed to compute zone heatmap: {e}"
        logger.error(f"heatmap_query_failed: {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error computing zone heatmap aggregations."
        )
