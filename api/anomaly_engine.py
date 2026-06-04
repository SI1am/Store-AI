import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from api.db import Database
from api.cache import CacheManager

logger = logging.getLogger(__name__)

class Anomaly(BaseModel):
    type: str
    severity: str
    description: str
    suggested_action: str
    detected_at: datetime
    value: Optional[float] = None
    threshold: Optional[str] = None

class AnomalyEngine:
    def __init__(self, db: Database, cache: CacheManager):
        self.db = db
        self.cache = cache

    async def detect_queue_spike(self, store_id: str) -> Optional[Anomaly]:
        """
        Detects checkout counter bottlenecks.
        Triggered when queue depth is sustained > 5 over the last 5 minutes.
        """
        try:
            # Look at last 5 minutes of queue depth entries
            # We query events inside BILLING zone over the last 5 minutes
            five_mins_ago = datetime.utcnow() - timedelta(minutes=5)
            query = """
                SELECT timestamp, metadata->>'queue_depth' as depth
                FROM events
                WHERE store_id = $1 AND zone_id = 'BILLING' AND event_type = 'BILLING_QUEUE_JOIN'
                  AND timestamp >= $2
                ORDER BY timestamp DESC;
            """
            records = await self.db.fetch_all(query, store_id, five_mins_ago)
            
            if not records:
                return None
                
            depths = [int(r['depth']) for r in records if r['depth'] is not None]
            
            # If we have multiple high samples, trigger spike warning
            high_samples = [d for d in depths if d > 5]
            if len(high_samples) >= 3:
                max_depth = max(depths)
                return Anomaly(
                    type="QUEUE_SPIKE",
                    severity="WARN",
                    description=f"Checkout queue depth sustained at {max_depth} (greater than threshold of 5).",
                    suggested_action="Open additional billing counters immediately.",
                    detected_at=datetime.utcnow(),
                    value=float(max_depth),
                    threshold="> 5"
                )
            return None
        except Exception as e:
            logger.warning(f"Queue spike anomaly detection failed: {e}")
            return None

    async def detect_conversion_drop(self, store_id: str) -> Optional[Anomaly]:
        """
        Detects conversions dropoffs.
        Triggered when today's conversion rate drops < 70% of the 7-day average.
        """
        try:
            today = datetime.utcnow().date()
            seven_days_ago = today - timedelta(days=7)
            
            # Query today's unique visitors and purchase conversions
            visitors_today_query = """
                SELECT COUNT(DISTINCT visitor_id) FROM events
                WHERE store_id = $1 AND event_type = 'ENTRY' AND is_staff = FALSE AND DATE(timestamp) = $2;
            """
            visitors_today = await self.db.fetch_val(visitors_today_query, store_id, today) or 0
            
            conversion_today_query = """
                WITH converted_visitors AS (
                    SELECT DISTINCT e.visitor_id
                    FROM events e
                    INNER JOIN pos_transactions p ON e.store_id = p.store_id
                    WHERE e.store_id = $1
                      AND e.event_type = 'BILLING_QUEUE_JOIN'
                      AND e.is_staff = FALSE
                      AND DATE(p.timestamp) = $2
                      AND e.timestamp BETWEEN (p.timestamp - INTERVAL '5 minutes') AND p.timestamp
                )
                SELECT COUNT(*) FROM converted_visitors;
            """
            converted_today = await self.db.fetch_val(conversion_today_query, store_id, today) or 0
            
            today_rate = converted_today / visitors_today if visitors_today > 0 else 0.0
            
            # Query 7-day historical unique visitors and conversions (excluding today)
            visitors_hist_query = """
                SELECT COUNT(DISTINCT visitor_id) FROM events
                WHERE store_id = $1 AND event_type = 'ENTRY' AND is_staff = FALSE 
                  AND DATE(timestamp) BETWEEN $2 AND $3;
            """
            visitors_hist = await self.db.fetch_val(visitors_hist_query, store_id, seven_days_ago, today - timedelta(days=1)) or 0
            
            conversion_hist_query = """
                WITH converted_visitors AS (
                    SELECT DISTINCT e.visitor_id
                    FROM events e
                    INNER JOIN pos_transactions p ON e.store_id = p.store_id
                    WHERE e.store_id = $1
                      AND e.event_type = 'BILLING_QUEUE_JOIN'
                      AND e.is_staff = FALSE
                      AND DATE(p.timestamp) BETWEEN $2 AND $3
                      AND e.timestamp BETWEEN (p.timestamp - INTERVAL '5 minutes') AND p.timestamp
                )
                SELECT COUNT(*) FROM converted_visitors;
            """
            converted_hist = await self.db.fetch_val(conversion_hist_query, store_id, seven_days_ago, today - timedelta(days=1)) or 0
            
            hist_rate = converted_hist / visitors_hist if visitors_hist > 0 else 0.0
            
            # Trigger drop alert if today's rate is under 70% of historical average (and we have enough baseline visitors)
            if hist_rate > 0.0 and today_rate < (hist_rate * 0.70) and visitors_today > 10:
                threshold_val = hist_rate * 0.70
                return Anomaly(
                    type="CONVERSION_DROP",
                    severity="CRITICAL",
                    description=f"Store checkout conversion rate fell to {today_rate:.1%} vs 7-day average of {hist_rate:.1%}.",
                    suggested_action="Review checkout staffing, floor assistance, or promotional layouts.",
                    detected_at=datetime.utcnow(),
                    value=today_rate,
                    threshold=f"< {threshold_val:.1%}"
                )
            return None
        except Exception as e:
            logger.warning(f"Conversion drop anomaly detection failed: {e}")
            return None

    async def detect_dead_zones(self, store_id: str) -> List[Anomaly]:
        """
        Detects cold departments/dead zones.
        Triggered for zones experiencing zero shopper visits in the last 30 minutes.
        """
        anomalies = []
        try:
            thirty_mins_ago = datetime.utcnow() - timedelta(minutes=30)
            
            # Query all zones that have active exit/entry metrics in the store historically
            all_zones_query = """
                SELECT DISTINCT zone_id FROM events
                WHERE store_id = $1 AND zone_id IS NOT NULL AND zone_id != 'BILLING';
            """
            all_zones_records = await self.db.fetch_all(all_zones_query, store_id)
            all_zones = [r['zone_id'] for r in all_zones_records]
            
            if not all_zones:
                return []
                
            # Query zones visited in the last 30 minutes
            visited_query = """
                SELECT DISTINCT zone_id FROM events
                WHERE store_id = $1 AND event_type = 'ZONE_ENTER' AND timestamp >= $2;
            """
            visited_records = await self.db.fetch_all(visited_query, store_id, thirty_mins_ago)
            visited_zones = [r['zone_id'] for r in visited_records]
            
            dead_zones = set(all_zones) - set(visited_zones)
            
            for zone in dead_zones:
                anomalies.append(Anomaly(
                    type="DEAD_ZONE",
                    severity="INFO",
                    description=f"Department zone '{zone}' has recorded 0 visitor entries in the last 30 minutes.",
                    suggested_action="Verify camera alignment, department signage, or merchandise displays.",
                    detected_at=datetime.utcnow(),
                    threshold="> 0 entries"
                ))
        except Exception as e:
            logger.warning(f"Dead zones anomaly detection failed: {e}")
            
        return anomalies

    async def detect_traffic_surge(self, store_id: str) -> Optional[Anomaly]:
        """
        Detects foot traffic surges.
        Triggered when current hourly entries exceed 2x the 7-day hourly baseline.
        """
        try:
            now = datetime.utcnow()
            one_hour_ago = now - timedelta(hours=1)
            seven_days_ago = now - timedelta(days=7)
            
            # Current hour entries
            curr_entries_query = """
                SELECT COUNT(DISTINCT visitor_id) FROM events
                WHERE store_id = $1 AND event_type = 'ENTRY' AND is_staff = FALSE AND timestamp >= $2;
            """
            curr_entries = await self.db.fetch_val(curr_entries_query, store_id, one_hour_ago) or 0
            
            # Historical 7-day average hourly entries
            hist_entries_query = """
                SELECT COUNT(DISTINCT visitor_id) / 168.0 FROM events  -- 168 hours in 7 days
                WHERE store_id = $1 AND event_type = 'ENTRY' AND is_staff = FALSE AND timestamp >= $2;
            """
            hist_avg = float(await self.db.fetch_val(hist_entries_query, store_id, seven_days_ago) or 0.0)
            
            # Trigger alert on 2x surge (with a baseline of at least 5 shoppers)
            if hist_avg > 0.0 and curr_entries > (hist_avg * 2.0) and curr_entries > 5:
                return Anomaly(
                    type="TRAFFIC_SURGE",
                    severity="WARN",
                    description=f"Store entries surged to {curr_entries} shoppers/hour vs baseline of {hist_avg:.1f}/hour.",
                    suggested_action="Alert floor personnel to assist with increased shopper volume.",
                    detected_at=datetime.utcnow(),
                    value=float(curr_entries),
                    threshold=f"> {hist_avg * 2.0:.1f}"
                )
            return None
        except Exception as e:
            logger.warning(f"Traffic surge anomaly detection failed: {e}")
            return None

    async def detect_all(self, store_id: str) -> List[Anomaly]:
        """Runs all detection sub-routines concurrently and returns active anomalies."""
        anomalies = []
        
        spike = await self.detect_queue_spike(store_id)
        if spike:
            anomalies.append(spike)
            
        drop = await self.detect_conversion_drop(store_id)
        if drop:
            anomalies.append(drop)
            
        surge = await self.detect_traffic_surge(store_id)
        if surge:
            anomalies.append(surge)
            
        dead = await self.detect_dead_zones(store_id)
        anomalies.extend(dead)
        
        return anomalies
