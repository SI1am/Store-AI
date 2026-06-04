import os
import sys
import cv2
import logging
from datetime import datetime, timedelta

# Set up path so we can import from detection package
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detection.pipeline import DetectionPipeline
from detection.tracker import PersonTracker
from detection.zone_mapper import ZoneMapper
from detection.event_emitter import EventEmitter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def run_visualizer(video_path: str, camera_id: str):
    logger.info(f"Starting visualization on {video_path} using camera {camera_id}...")
    
    # 1. Setup Camera Configuration
    # We will simulate CAM 1 (Entry/Exit Doorway) or CAM 2 (Skin Care)
    if camera_id == "CAM1":
        entry_line_pct = [[0.0, 0.8], [1.0, 0.8]]
        zones_config = {
            "ST1008": {
                "frame_width": 1920,
                "frame_height": 1080,
                "entry_line": entry_line_pct,
                "zones": {}
            }
        }
    else:  # CAM2 or others with shelf zones
        entry_line_pct = [[0.0, 0.0], [0.0, 0.0]]
        zones_config = {
            "ST1008": {
                "frame_width": 1920,
                "frame_height": 1080,
                "entry_line": entry_line_pct,
                "zones": {
                    "department_zone": {
                        "type": "polygon",
                        "points": [[0.05, 0.05], [0.95, 0.05], [0.95, 0.95], [0.05, 0.95]]
                    }
                }
            }
        }

    # 2. Initialize Detection Pipeline
    # Using temp file for events output since we only care about GUI display
    pipeline = DetectionPipeline(
        model_path="models/yolov8n.pt",
        store_id="ST1008",
        camera_id=camera_id,
        zones_config=zones_config,
        output_path="data/clips/events_visualizer.jsonl"
    )

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error(f"Could not open video file: {video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    # Scale line segment coordinates to frame resolution
    line_start = (int(entry_line_pct[0][0] * frame_width), int(entry_line_pct[0][1] * frame_height))
    line_end = (int(entry_line_pct[1][0] * frame_width), int(entry_line_pct[1][1] * frame_height))

    logger.info(f"Video resolution: {frame_width}x{frame_height} at {fps} FPS")
    print("\n" + "="*60)
    print("   RETAIL INTELLIGENCE PIPELINE LIVE VISUALIZER   ")
    print("="*60)
    print("Instructions:")
    print("  * A window will open showing the video stream.")
    print("  * Tracked shoppers will be drawn with bounding boxes and unique visitor IDs.")
    print("  * Press 'q' key or 'ESC' to exit the visualizer.")
    print("="*60 + "\n")

    frame_idx = 0
    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
                
            frame_idx += 1
            
            # Step 1: Detect persons
            raw_dets = pipeline.detect_persons(frame)
            
            # Step 2: Track people
            tracked_persons = pipeline.tracker.update(raw_dets)
            
            # Create a copy for drawing overlays
            draw_frame = frame.copy()
            
            # Draw Geofence lines (Entry/Exit Boundary in Cyan)
            if camera_id == "CAM1":
                cv2.line(draw_frame, line_start, line_end, (255, 255, 0), 4)
                cv2.putText(draw_frame, "ENTRY / EXIT BOUNDARY", (50, line_start[1] - 15),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 0), 3)
            else:
                # Draw shelf boundary (Green)
                pts = np.array([[int(p[0]*frame_width), int(p[1]*frame_height)] for p in zones_config["ST1008"]["zones"]["department_zone"]["points"]], np.int32)
                cv2.polylines(draw_frame, [pts], True, (0, 255, 0), 3)
                cv2.putText(draw_frame, "SHELF ZONE: DEPARTMENT", (pts[0][0], pts[0][1] - 15),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)

            # Draw tracked persons
            for person in tracked_persons:
                t_id = person['track_id']
                center = person['center']
                xyxy = person['xyxy']
                conf = person['confidence']
                
                # Generate deterministic visitor hash
                visitor_id = pipeline.emitter.generate_visitor_id(t_id)
                
                # Convert coords to int
                x1, y1, x2, y2 = map(int, xyxy)
                cx, cy = map(int, center)
                
                # Draw Box (Magenta/Pink for high visibility)
                cv2.rectangle(draw_frame, (x1, y1), (x2, y2), (255, 0, 255), 3)
                
                # Draw center point
                cv2.circle(draw_frame, (cx, cy), 6, (0, 0, 255), -1)
                
                # Draw text background for ID
                label = f"{visitor_id} ({conf:.1%})"
                (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
                cv2.rectangle(draw_frame, (x1, y1 - 30), (x1 + w, y1), (255, 0, 255), -1)
                cv2.putText(draw_frame, label, (x1, y1 - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # Scale frame down for display to comfortably fit common screens (e.g. 1080p/768p monitor)
            display_width = 1280
            display_height = int(frame_height * (display_width / frame_width))
            display_frame = cv2.resize(draw_frame, (display_width, display_height))
            
            # Display current stats on screen
            cv2.rectangle(display_frame, (10, 10), (450, 90), (0, 0, 0), -1)
            cv2.putText(display_frame, f"Camera: {camera_id} | Frame: {frame_idx}", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(display_frame, f"Active Tracked Shoppers: {len(tracked_persons)}", (20, 70),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

            # Show GUI window
            cv2.imshow("StoreLens - Live Tracking Stream", display_frame)
            
            # 30 ms delay to mimic ~30fps clip playback
            key = cv2.waitKey(30) & 0xFF
            if key == ord('q') or key == 27:  # 'q' or ESC key
                logger.info("Visualizer stopped by user key input.")
                break
                
    except Exception as e:
        logger.error(f"Error during video visualization: {e}")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        logger.info("Visualizer resources cleaned up and closed.")

if __name__ == "__main__":
    # Run by default on CAM 1 (Entry Doorway) or CAM 2 (Skin Care)
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", default="CAM1", choices=["CAM1", "CAM2"], help="Camera ID to simulate")
    args = parser.parse_args()
    
    if args.camera == "CAM1":
        video_path = "data/clips/CCTV Footage/CAM 1.mp4"
    else:
        video_path = "data/clips/CCTV Footage/CAM 2.mp4"
        
    run_visualizer(video_path, args.camera)
