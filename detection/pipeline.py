import os
import cv2
import logging
import uuid
import structlog
from typing import Generator, List, Dict, Any, Tuple, Optional
from datetime import datetime, timedelta
import numpy as np

from detection.model_loader import ModelLoader
from detection.tracker import PersonTracker
from detection.schemas import Event
from detection.event_emitter import EventEmitter
from detection.zone_mapper import ZoneMapper

# Initialize structured logger
logger = structlog.get_logger()

class DetectionPipeline:
    def __init__(self, model_path: str, store_id: str, camera_id: str, zones_config: Dict[str, Any], output_path: str = "output.jsonl"):
        self.model_path = model_path
        self.store_id = store_id
        self.camera_id = camera_id
        
        # Core Components
        self.detector = None  # Lazy-loaded in detect_persons
        self.tracker = PersonTracker()
        self.emitter = EventEmitter(store_id, camera_id, output_path)
        self.zone_mapper = ZoneMapper(zones_config, store_id)
        
        # Load Video/Frame dimensions from config
        store_config = zones_config.get(store_id, {})
        self.frame_width = store_config.get("frame_width", 1920)
        self.frame_height = store_config.get("frame_height", 1080)
        
        # Setup Entry/Exit line (defaults to middle-bottom line of the frame)
        raw_line = store_config.get("entry_line", [[0.0, 0.8], [1.0, 0.8]])
        self.entry_line = [
            (raw_line[0][0] * self.frame_width, raw_line[0][1] * self.frame_height),
            (raw_line[1][0] * self.frame_width, raw_line[1][1] * self.frame_height)
        ]
        
        # State tracking per shopper (track_id)
        self.prev_centers: Dict[int, Tuple[float, float]] = {}
        self.zone_enter_times: Dict[int, Dict[str, datetime]] = {}  # {track_id: {zone_id: enter_time}}
        self.active_visitor_zones: Dict[int, List[str]] = {}  # {track_id: [zone_ids]}
        
        # Entry/Exit persistence to prevent duplicate entry/exit logs per shopper session
        self.has_entered: Dict[int, bool] = {}
        self.has_exited: Dict[int, bool] = {}
        self.track_start_times: Dict[int, datetime] = {}
        
        # Video Stats
        self.fps = 30.0
        self.frame_count = 0

    def read_frames(self, video_path: str) -> Generator[Tuple[int, np.ndarray], None, None]:
        """
        Opens a video file and yields (frame_number, frame) sequentially.
        Handles resources cleanly and raises FileNotFoundError if file is missing.
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found at: {video_path}")
            
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise IOError(f"Failed to open video cap for: {video_path}")
            
        # Extract video properties
        self.fps = float(cap.get(cv2.CAP_PROP_FPS)) or 30.0
        self.frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        logger.info("video_opened", path=video_path, fps=self.fps, total_frames=self.frame_count)
        
        frame_idx = 0
        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break
                yield frame_idx, frame
                frame_idx += 1
        finally:
            cap.release()
            logger.info("video_closed", path=video_path)

    def detect_persons(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Runs YOLOv8 person detection on a single frame.
        Returns a list of parsed detection dicts.
        """
        if self.detector is None:
            self.detector = ModelLoader.get_yolo_model(self.model_path)
            
        try:
            # classes=[0] targets person only
            results = self.detector(frame, verbose=False, classes=[0])
            detections = []
            
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    xyxy = box.xyxy[0].tolist()  # [x1, y1, x2, y2]
                    conf = float(box.conf[0])
                    
                    # Calculate center point
                    x_center = (xyxy[0] + xyxy[2]) / 2.0
                    y_center = (xyxy[1] + xyxy[3]) / 2.0
                    
                    detections.append({
                        'xyxy': xyxy,
                        'confidence': conf,
                        'center': (x_center, y_center)
                    })
            return detections
        except Exception as e:
            logger.warning("inference_failed", error=str(e))
            return []

    def process_clip(self, video_path: str, base_timestamp: Optional[datetime] = None, max_frames: Optional[int] = None) -> None:
        """Runs the entire video-to-event pipeline on a video clip, emitting structured events."""
        logger.info("pipeline_started", store_id=self.store_id, camera_id=self.camera_id, video=video_path)
        
        # Base timestamp to simulate real-time operations
        if base_timestamp is None:
            base_timestamp = datetime.utcnow()
        events_emitted = []
        total_events_emitted = 0
        
        try:
            for frame_idx, frame in self.read_frames(video_path):
                if max_frames is not None and frame_idx >= max_frames:
                    logger.info("max_frames_reached", max_frames=max_frames)
                    break
                # Calculate virtual frame timestamp based on FPS
                frame_ts = base_timestamp + timedelta(seconds=(frame_idx / self.fps))
                
                # Step 1: Detect persons
                raw_dets = self.detect_persons(frame)
                
                # Step 2: Track people
                tracked_persons = self.tracker.update(raw_dets)
                
                current_active_ids = set()
                
                for person in tracked_persons:
                    t_id = person['track_id']
                    center = person['center']
                    xyxy = person['xyxy']
                    conf = person['confidence']
                    current_active_ids.add(t_id)
                    
                    # Store track start time for shoppers
                    if t_id not in self.track_start_times:
                        self.track_start_times[t_id] = frame_ts
                        self.active_visitor_zones[t_id] = []
                        self.has_entered[t_id] = False
                        self.has_exited[t_id] = False
                        # If this is the entry doorway camera (CAM1), automatically trigger ENTRY event
                        if self.camera_id == "CAM1":
                            entry_evt = self.emitter.emit_entry_event(t_id, frame_ts, conf)
                            events_emitted.append(entry_evt)
                            self.has_entered[t_id] = True
                            logger.info("shopper_entry_auto", track_id=t_id, visitor_id=entry_evt.visitor_id, time=frame_ts.isoformat())

                    # Step 3: Check Line Crossing (ENTRY / EXIT)
                    prev_center = self.prev_centers.get(t_id)
                    if prev_center:
                        direction = EventEmitter.get_line_crossing_direction(prev_center, center, self.entry_line)
                        if direction == "ENTRY" and not self.has_entered[t_id]:
                            entry_evt = self.emitter.emit_entry_event(t_id, frame_ts, conf)
                            events_emitted.append(entry_evt)
                            self.has_entered[t_id] = True
                            logger.info("shopper_entry", track_id=t_id, visitor_id=entry_evt.visitor_id, time=frame_ts.isoformat())
                            
                        elif direction == "EXIT" and self.has_entered[t_id] and not self.has_exited[t_id]:
                            dwell_duration = int((frame_ts - self.track_start_times[t_id]).total_seconds() * 1000)
                            exit_evt = self.emitter.emit_exit_event(t_id, frame_ts, dwell_ms=dwell_duration, confidence=conf)
                            events_emitted.append(exit_evt)
                            self.has_exited[t_id] = True
                            logger.info("shopper_exit", track_id=t_id, visitor_id=exit_evt.visitor_id, dwell_ms=dwell_duration)
                            
                    self.prev_centers[t_id] = center
                    
                    # Step 4: Zone mapping
                    curr_zones = self.zone_mapper.get_point_in_zones(center[0], center[1])
                    prev_zones = self.active_visitor_zones.get(t_id, [])
                    
                    # Check for zone entry (zone is in current zones but wasn't in previous zones)
                    for z_id in curr_zones:
                        if z_id not in prev_zones:
                            # Enter zone
                            if t_id not in self.zone_enter_times:
                                self.zone_enter_times[t_id] = {}
                            self.zone_enter_times[t_id][z_id] = frame_ts
                            
                            event_type = 'BILLING_QUEUE_JOIN' if z_id == 'BILLING' else 'ZONE_ENTER'
                            zone_enter_evt = self.emitter.emit_zone_event(t_id, z_id, event_type, frame_ts, confidence=conf)
                            events_emitted.append(zone_enter_evt)
                            logger.info("zone_entry", track_id=t_id, zone=z_id, time=frame_ts.isoformat())
                            
                    # Check for zone exit (zone was in previous zones but isn't in current zones)
                    for z_id in prev_zones:
                        if z_id not in curr_zones:
                            # Exit zone
                            enter_time = self.zone_enter_times.get(t_id, {}).get(z_id, frame_ts)
                            dwell_duration = int((frame_ts - enter_time).total_seconds() * 1000)
                            
                            event_type = 'BILLING_QUEUE_ABANDON' if z_id == 'BILLING' else 'ZONE_EXIT'
                            zone_exit_evt = self.emitter.emit_zone_event(t_id, z_id, event_type, frame_ts, dwell_ms=dwell_duration, confidence=conf)
                            events_emitted.append(zone_exit_evt)
                            logger.info("zone_exit", track_id=t_id, zone=z_id, dwell_ms=dwell_duration)
                            
                    self.active_visitor_zones[t_id] = curr_zones
                
                # Check for tracks that disappeared/died to trigger automatic shop session EXIT cleanups
                dead_ids = set(self.prev_centers.keys()) - current_active_ids
                for d_id in dead_ids:
                    # Emit zone exits for any active zones they were in
                    active_zones = self.active_visitor_zones.get(d_id, [])
                    for z_id in active_zones:
                        enter_time = self.zone_enter_times.get(d_id, {}).get(z_id, frame_ts)
                        dwell_duration = int((frame_ts - enter_time).total_seconds() * 1000)
                        event_type = 'BILLING_QUEUE_ABANDON' if z_id == 'BILLING' else 'ZONE_EXIT'
                        zone_exit_evt = self.emitter.emit_zone_event(d_id, z_id, event_type, frame_ts, dwell_ms=dwell_duration, confidence=0.8)
                        events_emitted.append(zone_exit_evt)
                        logger.info("zone_exit_timeout", track_id=d_id, zone=z_id, dwell_ms=dwell_duration)

                    # Clean up coordinates
                    self.prev_centers.pop(d_id, None)
                    self.active_visitor_zones.pop(d_id, None)
                    # Trigger exits if person was tracked but didn't cross exit line explicitly
                    if self.has_entered.get(d_id, False) and not self.has_exited.get(d_id, False):
                        dwell_duration = int((frame_ts - self.track_start_times[d_id]).total_seconds() * 1000)
                        exit_evt = self.emitter.emit_exit_event(d_id, frame_ts, dwell_ms=dwell_duration, confidence=0.8)
                        events_emitted.append(exit_evt)
                        self.has_exited[d_id] = True
                        logger.info("shopper_exit_timeout", track_id=d_id, visitor_id=exit_evt.visitor_id, dwell_ms=dwell_duration)
                
                # Periodically write events to avoid memory buildup
                if len(events_emitted) >= 50:
                    self.emitter.write_events(events_emitted)
                    total_events_emitted += len(events_emitted)
                    events_emitted = []

                # Periodic progress logging
                if frame_idx % 30 == 0:
                    logger.info("pipeline_progress", frame=frame_idx, active_shoppers=len(current_active_ids), events_count=(total_events_emitted + len(events_emitted)))
                    
        except KeyboardInterrupt:
            logger.info("pipeline_interrupted")
        finally:
            # Flush all remaining active tracks as exiting the store and zones at the end of the video
            try:
                last_ts = locals().get('frame_ts', datetime.utcnow())
                for t_id in list(self.prev_centers.keys()):
                    # Emit zone exits
                    active_zones = self.active_visitor_zones.get(t_id, [])
                    for z_id in active_zones:
                        enter_time = self.zone_enter_times.get(t_id, {}).get(z_id, last_ts)
                        dwell_duration = int((last_ts - enter_time).total_seconds() * 1000)
                        event_type = 'BILLING_QUEUE_ABANDON' if z_id == 'BILLING' else 'ZONE_EXIT'
                        zone_exit_evt = self.emitter.emit_zone_event(t_id, z_id, event_type, last_ts, dwell_ms=dwell_duration, confidence=0.8)
                        events_emitted.append(zone_exit_evt)
                        logger.info("zone_exit_flush", track_id=t_id, zone=z_id, dwell_ms=dwell_duration)
                        
                    # Emit store exits
                    if self.has_entered.get(t_id, False) and not self.has_exited.get(t_id, False):
                        dwell_duration = int((last_ts - self.track_start_times[t_id]).total_seconds() * 1000)
                        exit_evt = self.emitter.emit_exit_event(t_id, last_ts, dwell_ms=dwell_duration, confidence=0.8)
                        events_emitted.append(exit_evt)
                        self.has_exited[t_id] = True
                        logger.info("shopper_exit_flush", track_id=t_id, visitor_id=exit_evt.visitor_id, dwell_ms=dwell_duration)
            except Exception as e:
                logger.warning("flush_active_tracks_failed", error=str(e))

            # Write all events atomically to JSONL file
            if events_emitted:
                self.emitter.write_events(events_emitted)
                total_events_emitted += len(events_emitted)
            logger.info("pipeline_completed", total_events=total_events_emitted)
