import logging
import json
from datetime import datetime, date as date_type
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, Depends, HTTPException, status

from api.db import Database
from api.cache import CacheManager

router = APIRouter(tags=["Analytics"])
logger = logging.getLogger(__name__)

async def get_db(request: Request) -> Database:
    return request.app.state.db

async def get_cache(request: Request) -> CacheManager:
    return request.app.state.cache

@router.get("/stores/{store_id}/metrics")
async def get_store_metrics(
    store_id: str,
    date: Optional[str] = None,
    include_staff: bool = False,
    db: Database = Depends(get_db),
    cache: CacheManager = Depends(get_cache)
):
    """
    Computes and returns daily retail metrics for a store.
    Utilizes Cache-Aside pattern with a 60-second Redis TTL.
    """
    # 1. Parse date or default to today's date
    query_date_str = date or datetime.utcnow().strftime("%Y-%m-%d")
    try:
        query_date = datetime.strptime(query_date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Date must be in YYYY-MM-DD format."
        )

    # 2. Check Cache
    cache_key = f"metrics:{store_id}:{query_date_str}:{include_staff}"
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
                    "cached": True,
                    "cache_ttl_seconds": 60
                }
            }
        except Exception:
            logger.warning("failed_to_parse_cached_metrics")

    # 3. Database Computations (Non-blocking asyncpg queries)
    staff_filter = "" if include_staff else "AND is_staff = FALSE"
    e_staff_filter = "" if include_staff else "AND e.is_staff = FALSE"

    # A. Unique Shoppers (exclude employees)
    shopper_query = f"""
        SELECT COUNT(DISTINCT visitor_id) FROM events
        WHERE store_id = $1 AND event_type = 'ENTRY' {staff_filter} AND DATE(timestamp) = $2;
    """
    unique_visitors = await db.fetch_val(shopper_query, store_id, query_date) or 0

    # B. POS Sales Conversions (shopper enters queue within 5 mins of checkout time)
    conversion_query = f"""
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
    converted = await db.fetch_val(conversion_query, store_id, query_date) or 0

    # C. Average Dwell Duration per department zone (milliseconds)
    dwell_query = f"""
        SELECT zone_id, AVG(dwell_ms) as avg_dwell
        FROM events
        WHERE store_id = $1 AND event_type = 'ZONE_EXIT' {staff_filter} AND DATE(timestamp) = $2
        GROUP BY zone_id;
    """
    dwell_records = await db.fetch_all(dwell_query, store_id, query_date)
    avg_dwell_per_zone = {}
    for r in dwell_records:
        zone = r["zone_id"]
        if zone:
            avg_dwell_per_zone[zone] = round(float(r["avg_dwell"]), 2)

    # D. Real-time checkout queue depth
    queue_query = f"""
        SELECT COUNT(*) FROM events
        WHERE store_id = $1 AND zone_id = 'BILLING' AND event_type = 'ZONE_ENTER' {staff_filter}
          AND NOT EXISTS (
              SELECT 1 FROM events e2
              WHERE e2.visitor_id = events.visitor_id
                AND e2.zone_id = 'BILLING' AND e2.event_type = 'ZONE_EXIT' AND e2.timestamp > events.timestamp
          );
    """
    queue_depth = await db.fetch_val(queue_query, store_id) or 0

    # E. Checkout Counter Abandonment Rate
    abandonment_query = f"""
        SELECT COUNT(DISTINCT visitor_id) FROM events
        WHERE store_id = $1 AND event_type = 'BILLING_QUEUE_ABANDON' {staff_filter} AND DATE(timestamp) = $2;
    """
    abandonments = await db.fetch_val(abandonment_query, store_id, query_date) or 0

    # F. Peak Hour Traffic
    peak_query = f"""
        SELECT EXTRACT(HOUR FROM timestamp) as hour, COUNT(DISTINCT visitor_id) as count
        FROM events
        WHERE store_id = $1 AND event_type = 'ENTRY' {staff_filter} AND DATE(timestamp) = $2
        GROUP BY hour
        ORDER BY count DESC
        LIMIT 1;
    """
    peak_record = await db.fetch_one(peak_query, store_id, query_date)
    if peak_record:
        peak_hour = f"{int(peak_record['hour']):02d}:00"
        peak_hour_visitors = int(peak_record['count'])
    else:
        peak_hour = "00:00"
        peak_hour_visitors = 0

    # 4. Safe divisions
    conversion_rate = round(converted / unique_visitors, 4) if unique_visitors > 0 else 0.0
    
    total_checkout_attempts = abandonments + converted
    abandonment_rate = round(abandonments / total_checkout_attempts, 4) if total_checkout_attempts > 0 else 0.0

    # Assemble payload
    payload = {
        "store_id": store_id,
        "date": query_date_str,
        "unique_visitors": unique_visitors,
        "conversion_rate": conversion_rate,
        "avg_dwell_per_zone": avg_dwell_per_zone,
        "queue_depth": queue_depth,
        "abandonment_rate": abandonment_rate,
        "peak_hour": peak_hour,
        "peak_hour_visitors": peak_hour_visitors
    }

    # 5. Cache result for 60 seconds
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


@router.get("/stores/{store_id}/dates")
async def get_store_dates(
    store_id: str,
    db: Database = Depends(get_db)
):
    """
    Returns a list of all unique dates that have events for the store.
    """
    try:
        query = """
            SELECT DISTINCT DATE(timestamp) as date_val 
            FROM events 
            WHERE store_id = $1 
            ORDER BY date_val DESC;
        """
        records = await db.fetch_all(query, store_id)
        dates = [r["date_val"].strftime("%Y-%m-%d") for r in records if r["date_val"]]
        # Ensure we always return at least today's date
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        if today_str not in dates:
            dates.insert(0, today_str)
        return {
            "status": "ok",
            "data": dates
        }
    except Exception as e:
        logger.error(f"Failed to fetch store dates: {e}")
        return {
            "status": "ok",
            "data": [datetime.utcnow().strftime("%Y-%m-%d")]
        }


from datetime import timedelta

@router.get("/stores/{store_id}/live-status")
async def get_store_live_status(
    store_id: str,
    db: Database = Depends(get_db),
    cache: CacheManager = Depends(get_cache)
):
    """
    Computes real-time live status for all cameras and active tracks in the store.
    """
    try:
        # 1. Fetch latest state of all visitors in the last 2 hours
        two_hours_ago = datetime.utcnow() - timedelta(hours=2)
        query = """
            WITH latest_events AS (
                SELECT DISTINCT ON (visitor_id) 
                    visitor_id, camera_id, zone_id, event_type, timestamp, is_staff, confidence
                FROM events
                WHERE store_id = $1 AND timestamp >= $2
                ORDER BY visitor_id, timestamp DESC
            )
            SELECT * FROM latest_events
            WHERE event_type IN ('ENTRY', 'ZONE_ENTER', 'BILLING_QUEUE_JOIN')
            ORDER BY timestamp DESC;
        """
        records = await db.fetch_all(query, store_id, two_hours_ago)
        
        # Organize active visitors by camera
        active_by_cam = {
            "CAM1": [],
            "CAM2": [],
            "CAM3": [],
            "CAM4": [],
            "CAM5": []
        }
        
        for r in records:
            cam = r["camera_id"]
            if cam in active_by_cam:
                active_by_cam[cam].append({
                    "visitor_id": r["visitor_id"],
                    "zone_id": r["zone_id"],
                    "is_staff": r["is_staff"],
                    "entered_at": r["timestamp"].isoformat() + "Z",
                    "confidence": float(r["confidence"])
                })

        # 2. Build camera list with descriptions and zone info
        cameras_metadata = {
            "CAM1": {"name": "Main Entrance Doorway", "zone": "Entrance"},
            "CAM2": {"name": "Skin Care Section", "zone": "skin"},
            "CAM3": {"name": "Makeup Area", "zone": "makeup"},
            "CAM4": {"name": "Bath & Body Aisle", "zone": "bath-and-body"},
            "CAM5": {"name": "Billing Counter", "zone": "BILLING"}
        }

        # 3. Detect anomalies for correlation
        from api.anomaly_engine import AnomalyEngine
        engine = AnomalyEngine(db, cache)
        anomalies = await engine.detect_all(store_id)

        cameras_status = []
        for cam_id, meta in cameras_metadata.items():
            visitors = active_by_cam[cam_id]
            shoppers = [v for v in visitors if not v["is_staff"]]
            staff = [v for v in visitors if v["is_staff"]]
            
            # Find anomalies for this camera
            cam_anomalies = []
            for a in anomalies:
                if a.type == "DEAD_ZONE" and a.description.lower().find(meta["zone"].lower()) != -1:
                    cam_anomalies.append(a.model_dump())
                elif a.type == "QUEUE_SPIKE" and cam_id == "CAM5":
                    cam_anomalies.append(a.model_dump())
                elif a.type == "CONVERSION_DROP" and cam_id in ["CAM1", "CAM5"]:
                    cam_anomalies.append(a.model_dump())
            
            # Determine status
            if cam_anomalies:
                status_str = "ANOMALY_FLAGGED"
            elif len(shoppers) >= 5:
                status_str = "CROWDED"
            elif len(shoppers) > 0:
                status_str = "ACTIVE"
            else:
                status_str = "IDLE"

            cameras_status.append({
                "camera_id": cam_id,
                "name": meta["name"],
                "zone_id": meta["zone"],
                "status": status_str,
                "shoppers_count": len(shoppers),
                "staff_count": len(staff),
                "active_visitors": visitors,
                "anomalies": cam_anomalies
            })

        return {
            "status": "ok",
            "data": {
                "store_id": store_id,
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "cameras": cameras_status,
                "total_active_shoppers": sum(c["shoppers_count"] for c in cameras_status),
                "total_active_staff": sum(c["staff_count"] for c in cameras_status)
            }
        }
    except Exception as e:
        logger.error(f"Failed to compile live-status: {e}")
        return {
            "status": "error",
            "message": str(e)
        }
