import uuid
import logging
from typing import List, Dict, Any, Tuple
from datetime import datetime
from detection.schemas import Event

logger = logging.getLogger(__name__)

class GroupDetector:
    def __init__(self, line_points: List[Tuple[float, float]], frame_height: int, max_group_size: int = 5):
        self.line_points = line_points
        self.frame_height = frame_height
        self.max_group_size = max_group_size
        
        # Buffer to keep track of recent crossings: {frame_idx: [track_ids]}
        self.recent_crossings: Dict[int, List[Dict[str, Any]]] = {}
        # Window size (3 consecutive frames)
        self.window_size = 3

    def detect_group_crossings(self, crossings_in_frame: List[Dict[str, Any]], frame_idx: int) -> List[Dict[str, Any]]:
        """
        Processes shoppers crossing in the current frame.
        If multiple shoppers cross the entry line within 3 frames, groups them under a common group ID.
        """
        # Store current frame crossings: list of {'track_id', 'confidence'}
        if crossings_in_frame:
            self.recent_crossings[frame_idx] = crossings_in_frame

        # Clean up older buffered frames
        oldest_frame_allowed = frame_idx - self.window_size
        expired_frames = [f for f in self.recent_crossings.keys() if f < oldest_frame_allowed]
        for f in expired_frames:
            self.recent_crossings.pop(f, None)

        # Pool all crossings inside the current window
        pooled_crossings = []
        for f_idx, crossings in self.recent_crossings.items():
            pooled_crossings.extend(crossings)

        # If 2 or more people crossed in this window, check if we should group them
        if len(pooled_crossings) >= 2:
            # Create a common group ID
            group_id = str(uuid.uuid4())
            track_ids = [c['track_id'] for c in pooled_crossings]
            avg_conf = sum(c.get('confidence', 1.0) for c in pooled_crossings) / len(pooled_crossings)
            
            logger.info("group_detected", group_id=group_id, members=track_ids)
            
            return [{
                'group_id': group_id,
                'track_ids': track_ids,
                'num_people': len(pooled_crossings),
                'crossing_frame': frame_idx,
                'confidence': avg_conf
            }]
            
        return []

    def emit_group_entries(self, group_crossing: Dict[str, Any], timestamp: datetime, store_id: str, camera_id: str) -> List[Event]:
        """Generates standard ENTRY Events enriched with group metadata for each group member."""
        events = []
        group_id = group_crossing['group_id']
        group_size = group_crossing['num_people']
        confidence = group_crossing['confidence']

        for track_id in group_crossing['track_ids']:
            # Create unique visitor ID deterministically or dynamically
            visitor_id = f"VIS_{hash(f'{store_id}_{track_id}') & 0xffffffffffff:012X}"
            
            evt = Event(
                store_id=store_id,
                camera_id=camera_id,
                visitor_id=visitor_id,
                event_type='ENTRY',
                timestamp=timestamp,
                confidence=confidence,
                metadata={
                    'group_id': group_id,
                    'group_size': group_size
                }
            )
            events.append(evt)
            
        return events
