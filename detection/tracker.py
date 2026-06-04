import numpy as np
from typing import List, Dict, Any, Tuple

def calculate_iou(box1: List[float], box2: List[float]) -> float:
    """Calculates the Intersection over Union (IoU) of two bounding boxes in [x1, y1, x2, y2] format."""
    x1_1, y1_1, x2_1, y2_1 = box1
    x1_2, y1_2, x2_2, y2_2 = box2

    # Determine the coordinates of the intersection rectangle
    x1_i = max(x1_1, x1_2)
    y1_i = max(y1_1, y1_2)
    x2_i = min(x2_1, x2_2)
    y2_i = min(y2_1, y2_2)

    # Compute area of intersection
    if x2_i < x1_i or y2_i < y1_i:
        return 0.0
    intersection_area = (x2_i - x1_i) * (y2_i - y1_i)

    # Compute area of both boxes
    box1_area = (x2_1 - x1_1) * (y2_1 - y1_1)
    box2_area = (x2_2 - x1_2) * (y2_2 - y1_2)

    # Compute IoU
    union_area = box1_area + box2_area - intersection_area
    if union_area <= 0.0:
        return 0.0
    return intersection_area / union_area

class PersonTracker:
    def __init__(self, conf_high: float = 0.5, conf_low: float = 0.1, frame_rate: int = 30):
        self.conf_high = conf_high
        self.conf_low = conf_low
        self.frame_rate = frame_rate
        
        self.next_id = 1
        # active_tracks: dict of {track_id: {box, center, confidence, last_seen_frame, age}}
        self.active_tracks: Dict[int, Dict[str, Any]] = {}
        # occluded_tracks: dict of {track_id: {box, center, confidence, last_seen_frame, age}}
        self.occluded_tracks: Dict[int, Dict[str, Any]] = {}
        
        self.frame_idx = 0
        self.max_occlusion_frames = 15

    def update(self, detections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Updates the tracker with the current frame's detections.
        Matches detections to existing tracks using IoU overlap and distance.
        """
        self.frame_idx += 1
        
        # Filter detections by confidence
        valid_dets = [d for d in detections if d.get('confidence', 0.0) >= self.conf_low]
        
        # Pool all current active and occluded tracks for matching
        all_tracks = {**self.active_tracks, **self.occluded_tracks}
        track_ids = list(all_tracks.keys())
        
        matched_dets: Dict[int, Dict[str, Any]] = {}
        unmatched_dets = []
        
        # Greedy matching based on IoU
        if valid_dets and track_ids:
            # Build IoU cost matrix
            cost_matrix = np.zeros((len(valid_dets), len(track_ids)))
            for d_idx, det in enumerate(valid_dets):
                for t_idx, t_id in enumerate(track_ids):
                    cost_matrix[d_idx, t_idx] = calculate_iou(det['xyxy'], all_tracks[t_id]['xyxy'])
            
            # Greedy association
            matched_det_indices = set()
            matched_track_indices = set()
            
            # Find high overlaps first
            flat_indices = np.argsort(-cost_matrix, axis=None)
            for idx in flat_indices:
                d_idx, t_idx = np.unravel_index(idx, cost_matrix.shape)
                iou = cost_matrix[d_idx, t_idx]
                
                if iou < 0.15:  # Minimum IoU overlap threshold
                    break
                    
                if d_idx in matched_det_indices or t_idx in matched_track_indices:
                    continue
                    
                t_id = track_ids[t_idx]
                matched_dets[t_id] = valid_dets[d_idx]
                matched_det_indices.add(d_idx)
                matched_track_indices.add(t_idx)
                
            for d_idx, det in enumerate(valid_dets):
                if d_idx not in matched_det_indices:
                    unmatched_dets.append(det)
        else:
            unmatched_dets = valid_dets

        # Update matched tracks
        updated_active = {}
        updated_occluded = {}
        
        for t_id, det in matched_dets.items():
            prev_track = all_tracks[t_id]
            updated_track = {
                'box_id': t_id,
                'xyxy': det['xyxy'],
                'confidence': det['confidence'],
                'center': det['center'],
                'last_seen_frame': self.frame_idx,
                'age': prev_track['age'] + 1
            }
            # Track is confirmed if it has been seen for at least frame_rate / 2 frames (or simply active)
            updated_track['is_confirmed'] = updated_track['age'] >= 5
            updated_active[t_id] = updated_track

        # Handle unmatched tracks (occlusion)
        for t_id, track in all_tracks.items():
            if t_id not in matched_dets:
                occluded_duration = self.frame_idx - track['last_seen_frame']
                if occluded_duration <= self.max_occlusion_frames:
                    track['age'] += 1
                    track['is_confirmed'] = False  # Suspended confirmation while occluded
                    updated_occluded[t_id] = track

        # Handle unmatched detections (new tracks)
        for det in unmatched_dets:
            # Only create new track if confidence is high enough
            if det.get('confidence', 0.0) >= self.conf_high:
                t_id = self.next_id
                self.next_id += 1
                new_track = {
                    'box_id': t_id,
                    'xyxy': det['xyxy'],
                    'confidence': det['confidence'],
                    'center': det['center'],
                    'last_seen_frame': self.frame_idx,
                    'age': 1,
                    'is_confirmed': False
                }
                updated_active[t_id] = new_track

        self.active_tracks = updated_active
        self.occluded_tracks = updated_occluded

        # Construct return payload
        results = []
        for t_id, track in self.active_tracks.items():
            results.append({
                'track_id': t_id,
                'xyxy': track['xyxy'],
                'confidence': track['confidence'],
                'center': track['center'],
                'is_confirmed': track['is_confirmed']
            })
        return results
