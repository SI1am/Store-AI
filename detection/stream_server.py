import os
import sys
import cv2
import time
import logging
import httpx
import asyncio
from datetime import datetime
from typing import AsyncGenerator
import uvicorn
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# Set up path so we can import from detection package
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detection.pipeline import DetectionPipeline
from detection.staff_classifier_enhanced import EnhancedStaffClassifier
from detection.event_emitter import EventEmitter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="StoreLens Live Camera Streaming Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup cameras configuration
camera_videos = {
    "CAM1": "data/clips/CCTV Footage/CAM 1.mp4",
    "CAM2": "data/clips/CCTV Footage/CAM 2.mp4",
    "CAM3": "data/clips/CCTV Footage/CAM 3.mp4",
    "CAM4": "data/clips/CCTV Footage/CAM 4.mp4",
    "CAM5": "data/clips/CCTV Footage/CAM 5.mp4",
}

# Geofence configuration matching standard run configurations
zones_configs = {
    "CAM1": {
        "entry_line": [[0.0, 0.8], [1.0, 0.8]],
        "zones": {}
    },
    "CAM2": {
        "entry_line": [[0.0, 0.0], [0.0, 0.0]],
        "zones": {
            "skin": {
                "type": "polygon",
                "points": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
            }
        }
    },
    "CAM3": {
        "entry_line": [[0.0, 0.0], [0.0, 0.0]],
        "zones": {
            "makeup": {
                "type": "polygon",
                "points": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
            }
        }
    },
    "CAM4": {
        "entry_line": [[0.0, 0.0], [0.0, 0.0]],
        "zones": {
            "bath-and-body": {
                "type": "polygon",
                "points": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
            }
        }
    },
    "CAM5": {
        "entry_line": [[0.0, 0.0], [0.0, 0.0]],
        "zones": {
            "BILLING": {
                "type": "polygon",
                "points": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
            }
        }
    }
}

def ingest_events_to_backend(events) -> None:
    if not events:
        return
    try:
        import json
        payload = {"events": [e.model_dump() for e in events]}
        payload_serialized = json.loads(json.dumps(payload, default=str))
        r = httpx.post("http://127.0.0.1:8000/api/v1/events/ingest", json=payload_serialized, timeout=2.0)
        if r.status_code != 200:
            logger.warning(f"Failed to ingest events: {r.status_code} - {r.text}")
        else:
            logger.info(f"Ingested {len(events)} events to backend successfully.")
    except Exception as e:
        logger.warning(f"API Ingestion request failed: {e}")


async def generate_frames(camera_id: str) -> AsyncGenerator[bytes, None]:
    """Generates JPEG frame byte sequences for MJPEG streaming with real-time analytics."""
    video_path = camera_videos.get(camera_id)
    if not video_path or not os.path.exists(video_path):
        logger.error(f"Video file not found for {camera_id}: {video_path}")
        return

    config = zones_configs.get(camera_id, {"entry_line": [[0.0, 0.0], [0.0, 0.0]], "zones": {}})
    pipeline = DetectionPipeline(
        model_path="models/yolov8n.pt",
        store_id="ST1008",
        camera_id=camera_id,
        zones_config={"ST1008": {**config, "frame_width": 1920, "frame_height": 1080}},
        output_path="data/clips/events_stream.jsonl"
    )

    staff_classifier = EnhancedStaffClassifier()
    track_history = {} # track_id: dict with keys trajectory, frame_count, active_zones, is_staff

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error(f"Failed to open video source: {video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    delay_sec = 1.0 / fps

    try:
        while cap.isOpened():
            start_time = time.perf_counter()
            ret, frame = cap.read()
            if not ret:
                # Loop back to beginning for continuous streaming
                # 1. Flush/emit exits for all active tracks to cleanly terminate their sessions in the DB
                events_to_flush = []
                last_ts = datetime.utcnow()
                for t_id in list(pipeline.prev_centers.keys()):
                    is_staff = track_history.get(t_id, {}).get("is_staff", False)
                    # Emit zone exits
                    active_zones = pipeline.active_visitor_zones.get(t_id, [])
                    for z_id in active_zones:
                        event_type = 'BILLING_QUEUE_ABANDON' if z_id == 'BILLING' else 'ZONE_EXIT'
                        evt = pipeline.emitter.emit_zone_event(t_id, z_id, event_type, last_ts, dwell_ms=1000, confidence=0.8, is_staff=is_staff)
                        events_to_flush.append(evt)
                    # Emit store exit
                    if pipeline.has_entered.get(t_id, False) and not pipeline.has_exited.get(t_id, False):
                        evt = pipeline.emitter.emit_exit_event(t_id, last_ts, dwell_ms=1000, confidence=0.8, is_staff=is_staff)
                        events_to_flush.append(evt)

                if events_to_flush:
                    ingest_events_to_backend(events_to_flush)
                    pipeline.emitter.write_events(events_to_flush)

                # 2. Reset tracking states
                pipeline.prev_centers.clear()
                pipeline.active_visitor_zones.clear()
                pipeline.track_start_times.clear()
                pipeline.has_entered.clear()
                pipeline.has_exited.clear()
                pipeline.zone_enter_times.clear()
                track_history.clear()

                # 3. Reset video capture and rotate salt
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                pipeline.emitter.salt = datetime.utcnow().strftime("%Y%m%d%H%M%S")
                continue

            frame_ts = datetime.utcnow()
            events_to_ingest = []

            # Run detection & tracking
            raw_dets = pipeline.detect_persons(frame)
            tracked_persons = pipeline.tracker.update(raw_dets)

            # Draw Overlays on Frame
            draw_frame = frame.copy()

            # Draw Geofence entry line (CAM 1) or Polygon (Other CAMs)
            if camera_id == "CAM1":
                line_y = int(0.8 * frame_height)
                cv2.line(draw_frame, (0, line_y), (frame_width, line_y), (255, 255, 0), 4)
                cv2.putText(draw_frame, "ENTRY / EXIT BOUNDARY", (50, line_y - 15),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 0), 3)
            else:
                zone_name = list(config["zones"].keys())[0]
                cv2.rectangle(draw_frame, (10, 10), (frame_width - 10, frame_height - 10), (0, 255, 0), 4)
                cv2.putText(draw_frame, f"ZONE: {zone_name.upper()}", (50, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)

            current_active_ids = set()

            # Draw tracked boxes & run real-time event logic
            for person in tracked_persons:
                t_id = person['track_id']
                center = person['center']
                xyxy = person['xyxy']
                conf = person['confidence']
                current_active_ids.add(t_id)

                # Initialize states if new track
                if t_id not in track_history:
                    pipeline.track_start_times[t_id] = frame_ts
                    pipeline.active_visitor_zones[t_id] = []
                    pipeline.has_entered[t_id] = False
                    pipeline.has_exited[t_id] = False
                    track_history[t_id] = {
                        "trajectory": [],
                        "frame_count": 0,
                        "active_zones": [],
                        "is_staff": False
                    }
                    # If doorway camera CAM1, emit entry event automatically
                    if camera_id == "CAM1":
                        entry_evt = pipeline.emitter.emit_entry_event(t_id, frame_ts, conf, is_staff=False)
                        events_to_ingest.append(entry_evt)
                        pipeline.has_entered[t_id] = True

                hist = track_history[t_id]
                hist["trajectory"].append(center)
                hist["frame_count"] += 1
                hist["y_center"] = center[1]

                # Run staff classifier
                x1, y1, x2, y2 = map(int, xyxy)
                cx, cy = map(int, center)
                
                # Check staff uniform based on cropped box patch every 5 frames
                if hist["frame_count"] >= 5 and hist["frame_count"] % 5 == 0:
                    patch = frame[max(0, y1):min(frame_height, y2), max(0, x1):min(frame_width, x2)]
                    res = staff_classifier.classify(patch, hist, frame_height, frame_width)
                    if res.is_staff != hist["is_staff"]:
                        hist["is_staff"] = res.is_staff
                        logger.info(f"Re-classified track {t_id} as staff: {res.is_staff} (reasoning: {res.reasoning})")
                        
                        # Emit a status update event immediately so the DB gets the new is_staff flag
                        active_zones = pipeline.active_visitor_zones.get(t_id, [])
                        if active_zones:
                            for z_id in active_zones:
                                event_type = "BILLING_QUEUE_JOIN" if z_id == "BILLING" else "ZONE_ENTER"
                                evt = pipeline.emitter.emit_zone_event(t_id, z_id, event_type, frame_ts, confidence=conf, is_staff=res.is_staff)
                                events_to_ingest.append(evt)
                        else:
                            evt = pipeline.emitter.emit_entry_event(t_id, frame_ts, conf, is_staff=res.is_staff)
                            events_to_ingest.append(evt)

                is_staff = hist["is_staff"]
                visitor_id = pipeline.emitter.generate_visitor_id(t_id)

                # Draw bounding box & track overlay
                box_color = (0, 165, 255) if is_staff else (255, 0, 255) # orange for staff, purple for customer
                role = "STAFF" if is_staff else "CUSTOMER"
                cv2.rectangle(draw_frame, (x1, y1), (x2, y2), box_color, 3)
                cv2.circle(draw_frame, (cx, cy), 6, (0, 0, 255), -1)
                
                label = f"{role}: {visitor_id}"
                (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
                cv2.rectangle(draw_frame, (x1, y1 - 30), (x1 + w, y1), box_color, -1)
                cv2.putText(draw_frame, label, (x1, y1 - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

                # Check line crossing for doorway cam
                prev_center = pipeline.prev_centers.get(t_id)
                if prev_center:
                    direction = EventEmitter.get_line_crossing_direction(prev_center, center, pipeline.entry_line)
                    if direction == "ENTRY" and not pipeline.has_entered[t_id]:
                        entry_evt = pipeline.emitter.emit_entry_event(t_id, frame_ts, conf, is_staff=is_staff)
                        events_to_ingest.append(entry_evt)
                        pipeline.has_entered[t_id] = True
                    elif direction == "EXIT" and pipeline.has_entered[t_id] and not pipeline.has_exited[t_id]:
                        dwell_duration = int((frame_ts - pipeline.track_start_times[t_id]).total_seconds() * 1000)
                        exit_evt = pipeline.emitter.emit_exit_event(t_id, frame_ts, dwell_ms=dwell_duration, confidence=conf, is_staff=is_staff)
                        events_to_ingest.append(exit_evt)
                        pipeline.has_exited[t_id] = True

                pipeline.prev_centers[t_id] = center

                # Map to zones
                curr_zones = pipeline.zone_mapper.get_point_in_zones(center[0], center[1])
                hist["active_zones"] = list(set(hist["active_zones"] + curr_zones))
                prev_zones = pipeline.active_visitor_zones.get(t_id, [])

                # Zone entries
                for z_id in curr_zones:
                    if z_id not in prev_zones:
                        pipeline.zone_enter_times.setdefault(t_id, {})[z_id] = frame_ts
                        event_type = "BILLING_QUEUE_JOIN" if z_id == "BILLING" else "ZONE_ENTER"
                        evt = pipeline.emitter.emit_zone_event(t_id, z_id, event_type, frame_ts, confidence=conf, is_staff=is_staff)
                        events_to_ingest.append(evt)

                # Zone exits
                for z_id in prev_zones:
                    if z_id not in curr_zones:
                        enter_time = pipeline.zone_enter_times.get(t_id, {}).get(z_id, frame_ts)
                        dwell_duration = int((frame_ts - enter_time).total_seconds() * 1000)
                        event_type = "BILLING_QUEUE_ABANDON" if z_id == "BILLING" else "ZONE_EXIT"
                        evt = pipeline.emitter.emit_zone_event(t_id, z_id, event_type, frame_ts, dwell_ms=dwell_duration, confidence=conf, is_staff=is_staff)
                        events_to_ingest.append(evt)

                pipeline.active_visitor_zones[t_id] = curr_zones

            # Clean up dead tracks
            dead_ids = set(pipeline.prev_centers.keys()) - current_active_ids
            for d_id in dead_ids:
                is_staff = track_history.get(d_id, {}).get("is_staff", False)
                active_zones = pipeline.active_visitor_zones.get(d_id, [])
                for z_id in active_zones:
                    enter_time = pipeline.zone_enter_times.get(d_id, {}).get(z_id, frame_ts)
                    dwell_duration = int((frame_ts - enter_time).total_seconds() * 1000)
                    event_type = "BILLING_QUEUE_ABANDON" if z_id == "BILLING" else "ZONE_EXIT"
                    evt = pipeline.emitter.emit_zone_event(d_id, z_id, event_type, frame_ts, dwell_ms=dwell_duration, confidence=0.8, is_staff=is_staff)
                    events_to_ingest.append(evt)
                
                if pipeline.has_entered.get(d_id, False) and not pipeline.has_exited.get(d_id, False):
                    dwell_duration = int((frame_ts - pipeline.track_start_times[d_id]).total_seconds() * 1000)
                    exit_evt = pipeline.emitter.emit_exit_event(d_id, frame_ts, dwell_ms=dwell_duration, confidence=0.8, is_staff=is_staff)
                    events_to_ingest.append(exit_evt)
                    pipeline.has_exited[d_id] = True

                pipeline.prev_centers.pop(d_id, None)
                pipeline.active_visitor_zones.pop(d_id, None)
                pipeline.track_start_times.pop(d_id, None)
                pipeline.has_entered.pop(d_id, None)
                pipeline.has_exited.pop(d_id, None)
                track_history.pop(d_id, None)

            # Ingest events to backend API and append to local stream file
            if events_to_ingest:
                ingest_events_to_backend(events_to_ingest)
                pipeline.emitter.write_events(events_to_ingest)

            # Resize frame down for network bandwidth optimization (e.g. 640x360)
            compressed_frame = cv2.resize(draw_frame, (640, 360))
            
            # Encode frame to JPEG
            ret_enc, jpeg = cv2.imencode('.jpg', compressed_frame)
            if not ret_enc:
                continue

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

            # Sleep to match frame rate exactly
            elapsed = time.perf_counter() - start_time
            sleep_time = max(0.0, delay_sec - elapsed)
            await asyncio.sleep(sleep_time)

    finally:
        # Flush/emit exits for all active tracks to cleanly terminate their sessions in the DB when generator is closed
        events_to_flush = []
        last_ts = datetime.utcnow()
        for t_id in list(pipeline.prev_centers.keys()):
            is_staff = track_history.get(t_id, {}).get("is_staff", False)
            # Emit zone exits
            active_zones = pipeline.active_visitor_zones.get(t_id, [])
            for z_id in active_zones:
                event_type = 'BILLING_QUEUE_ABANDON' if z_id == 'BILLING' else 'ZONE_EXIT'
                evt = pipeline.emitter.emit_zone_event(t_id, z_id, event_type, last_ts, dwell_ms=1000, confidence=0.8, is_staff=is_staff)
                events_to_flush.append(evt)
            # Emit store exit
            if pipeline.has_entered.get(t_id, False) and not pipeline.has_exited.get(t_id, False):
                evt = pipeline.emitter.emit_exit_event(t_id, last_ts, dwell_ms=1000, confidence=0.8, is_staff=is_staff)
                events_to_flush.append(evt)

        if events_to_flush:
            try:
                ingest_events_to_backend(events_to_flush)
                pipeline.emitter.write_events(events_to_flush)
            except Exception as ex:
                logger.warning(f"Failed to ingest/write final events: {ex}")
        cap.release()

@app.get("/stream/{camera_id}")
def stream_camera(camera_id: str):
    """Endpoints providing live MJPEG stream response for standard img elements."""
    if camera_id not in camera_videos:
        return Response(status_code=404, content=f"Camera ID '{camera_id}' not found.")
    return StreamingResponse(generate_frames(camera_id), media_type="multipart/x-mixed-replace; boundary=frame")

if __name__ == "__main__":
    logger.info("Starting live cameras streaming server on host port 8001...")
    uvicorn.run(app, host="127.0.0.1", port=8001)
