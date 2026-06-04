import os
import json
import hashlib
import logging
import tempfile
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from detection.schemas import Event

logger = logging.getLogger(__name__)

def cross_product(p1: Tuple[float, float], p2: Tuple[float, float], p3: Tuple[float, float]) -> float:
    """Calculates cross product of vectors p1p2 and p1p3."""
    return (p2[0] - p1[0]) * (p3[1] - p1[1]) - (p2[1] - p1[1]) * (p3[0] - p1[0])

def intersect(a: Tuple[float, float], b: Tuple[float, float], c: Tuple[float, float], d: Tuple[float, float]) -> bool:
    """Returns True if line segment AB intersects with line segment CD."""
    return (
        ((cross_product(a, b, c) > 0) != (cross_product(a, b, d) > 0)) and
        ((cross_product(c, d, a) > 0) != (cross_product(c, d, b) > 0))
    )

class EventEmitter:
    def __init__(self, store_id: str, camera_id: str, output_path: str):
        self.store_id = store_id
        self.camera_id = camera_id
        self.output_path = output_path
        
        # Salt to keep hashing deterministic per run but unique across runs
        self.salt = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        
        # Ensure parent folder of output_path exists
        out_dir = os.path.dirname(output_path)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)

    def generate_visitor_id(self, track_id: int) -> str:
        """Generates a deterministic 12-character visitor hash from track_id and context."""
        payload = f"{self.store_id}_{self.camera_id}_{track_id}_{self.salt}"
        hasher = hashlib.sha256(payload.encode('utf-8'))
        sha_hex = hasher.hexdigest().upper()
        # Return VIS_ followed by first 12 characters of hash
        return f"VIS_{sha_hex[:12]}"

    def emit_entry_event(self, track_id: int, frame_ts: datetime, confidence: float, is_staff: bool = False, metadata: Optional[Dict[str, Any]] = None) -> Event:
        """Helper to construct an ENTRY Event."""
        return Event(
            store_id=self.store_id,
            camera_id=self.camera_id,
            visitor_id=self.generate_visitor_id(track_id),
            event_type='ENTRY',
            timestamp=frame_ts,
            confidence=confidence,
            is_staff=is_staff,
            metadata=metadata or {}
        )

    def emit_exit_event(self, track_id: int, frame_ts: datetime, dwell_ms: int, confidence: float = 1.0, is_staff: bool = False, metadata: Optional[Dict[str, Any]] = None) -> Event:
        """Helper to construct an EXIT Event."""
        return Event(
            store_id=self.store_id,
            camera_id=self.camera_id,
            visitor_id=self.generate_visitor_id(track_id),
            event_type='EXIT',
            timestamp=frame_ts,
            dwell_ms=dwell_ms,
            confidence=confidence,
            is_staff=is_staff,
            metadata=metadata or {}
        )

    def emit_zone_event(self, track_id: int, zone_id: str, event_type: str, frame_ts: datetime, dwell_ms: int = 0, confidence: float = 1.0, is_staff: bool = False, metadata: Optional[Dict[str, Any]] = None) -> Event:
        """Helper to construct a ZONE Event (ZONE_ENTER, ZONE_EXIT, ZONE_DWELL)."""
        assert event_type in ['ZONE_ENTER', 'ZONE_EXIT', 'ZONE_DWELL', 'BILLING_QUEUE_JOIN', 'BILLING_QUEUE_ABANDON']
        return Event(
            store_id=self.store_id,
            camera_id=self.camera_id,
            visitor_id=self.generate_visitor_id(track_id),
            event_type=event_type,
            timestamp=frame_ts,
            zone_id=zone_id,
            dwell_ms=dwell_ms,
            confidence=confidence,
            is_staff=is_staff,
            metadata=metadata or {}
        )

    def write_events(self, events: List[Event]) -> None:
        """
        Appends a list of Events to the output JSONL file using high-performance append.
        """
        if not events:
            return

        new_lines = [e.model_dump_json() + "\n" for e in events]
        try:
            with open(self.output_path, 'a', encoding='utf-8') as f:
                f.writelines(new_lines)
            logger.info(f"Appended {len(events)} events to {self.output_path}")
        except Exception as e:
            error_msg = f"Failed to append events to {self.output_path}: {e}"
            logger.error(error_msg)
            raise IOError(error_msg) from e

    @staticmethod
    def get_line_crossing_direction(prev_center: Tuple[float, float], curr_center: Tuple[float, float], line_points: List[Tuple[float, float]]) -> Optional[str]:
        """
        Determines line-crossing direction (ENTRY, EXIT, or None) using vector cross product.
        - line_points must have format [(x1, y1), (x2, y2)]
        """
        if len(line_points) != 2:
            return None

        lp1, lp2 = line_points[0], line_points[1]

        # Check if segment between previous center and current center intersects the entry/exit line
        if not intersect(prev_center, curr_center, lp1, lp2):
            return None

        # Cross product to check direction:
        # A positive cross product implies point is on one side, negative on the other.
        # Vector lp1 -> lp2 crossed with vector lp1 -> curr_center
        direction = cross_product(lp1, lp2, curr_center)
        if direction < 0:
            return "ENTRY"
        elif direction > 0:
            return "EXIT"
        return None
