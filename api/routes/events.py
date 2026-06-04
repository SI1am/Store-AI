import logging
from datetime import datetime
from typing import List
from fastapi import APIRouter, Request, Depends, HTTPException, status
from pydantic import BaseModel, Field

from detection.schemas import Event
from api.db import Database
from api.cache import CacheManager

router = APIRouter(tags=["Events"])
logger = logging.getLogger(__name__)

# Request Schema for bulk ingestion
class EventIngestRequest(BaseModel):
    events: List[Event] = Field(..., max_items=500)

async def get_db(request: Request) -> Database:
    return request.app.state.db

async def get_cache(request: Request) -> CacheManager:
    return request.app.state.cache

@router.post("/events/ingest", status_code=status.HTTP_200_OK)
async def ingest_events(
    batch: EventIngestRequest,
    request: Request,
    db: Database = Depends(get_db),
    cache: CacheManager = Depends(get_cache)
):
    """
    Bulk ingest shopping metrics events with immediate Redis deduplication and asyncpg batch insertions.
    """
    trace_id = request.scope.get("trace_id", "N/A")
    new_events: List[Event] = []
    duplicate_count = 0
    
    # 1. Deduplication check in Redis
    for event in batch.events:
        event_id_str = str(event.event_id)
        # Check if already seen
        is_duplicate = await cache.sismember("processed_events", event_id_str)
        if is_duplicate:
            duplicate_count += 1
        else:
            new_events.append(event)
            # Cache event ID with 24-hour TTL in processed set
            await cache.sadd("processed_events", event_id_str)

    # 2. Batch insertion to PostgreSQL
    if new_events:
        # Prepare parameters for asyncpg executemany
        # Order must match the database insert columns
        insert_query = """
            INSERT INTO events (
                event_id, trace_id, store_id, camera_id, visitor_id, 
                event_type, timestamp, zone_id, dwell_ms, is_staff, confidence, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (event_id) DO NOTHING;
        """
        
        insert_params = []
        for e in new_events:
            insert_params.append((
                str(e.event_id),
                trace_id,
                e.store_id,
                e.camera_id,
                e.visitor_id,
                e.event_type,
                e.timestamp,
                e.zone_id,
                e.dwell_ms,
                e.is_staff,
                e.confidence,
                json_dumps(e.metadata) if hasattr(e, 'metadata') else '{}'
            ))
            
        try:
            # Batch execute insertions
            await db.executemany(insert_query, insert_params)
            
            # Propagate is_staff update to all past events of these visitors
            update_query = "UPDATE events SET is_staff = $1 WHERE visitor_id = $2;"
            update_params = [(e.is_staff, e.visitor_id) for e in new_events]
            await db.executemany(update_query, update_params)
            
            logger.info("bulk_events_ingested", count=len(new_events), duplicates=duplicate_count)
        except Exception as e:
            error_msg = f"Failed to batch insert events into database: {e}"
            logger.error(f"ingest_db_failed: {error_msg} | trace_id: {trace_id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to persist events in database."
            )
            
    # Return envelope format
    return {
        "status": "ok",
        "data": {
            "ingested": len(new_events),
            "duplicates": duplicate_count,
            "total": len(batch.events)
        },
        "meta": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "trace_id": trace_id
        }
    }

def json_dumps(data: dict) -> str:
    """Helper to convert dict metadata to json string."""
    import json
    return json.dumps(data)
