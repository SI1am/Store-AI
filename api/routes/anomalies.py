import logging
from datetime import datetime
from fastapi import APIRouter, Request, Depends, status

from api.db import Database
from api.cache import CacheManager
from api.anomaly_engine import AnomalyEngine

router = APIRouter(tags=["Alerts"])
logger = logging.getLogger(__name__)

async def get_db(request: Request) -> Database:
    return request.app.state.db

async def get_cache(request: Request) -> CacheManager:
    return request.app.state.cache

@router.get("/stores/{store_id}/anomalies")
async def get_store_anomalies(
    store_id: str,
    db: Database = Depends(get_db),
    cache: CacheManager = Depends(get_cache)
):
    """
    Computes real-time operational store anomalies.
    Returns queue spikes, conversions dropoffs, cold zones, and traffic surges.
    """
    trace_id = "LIVE"
    engine = AnomalyEngine(db, cache)
    
    # Trigger real-time detections
    anomalies = await engine.detect_all(store_id)
    
    # Check if there are any critical anomalies
    has_critical = any(a.severity == "CRITICAL" for a in anomalies)
    
    return {
        "status": "ok",
        "data": {
            "store_id": store_id,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "anomalies": [a.model_dump() for a in anomalies],
            "has_critical": has_critical
        },
        "meta": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "trace_id": trace_id,
            "cached": False
        }
    }
