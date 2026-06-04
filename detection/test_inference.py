import os
import sys
import time
import argparse
import numpy as np
import cv2
from typing import Optional

# Set up path so we can import from detection package
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from detection.model_loader import ModelLoader

def get_memory_usage_mb() -> float:
    """Returns memory usage of current process in MB, working on both Windows and Linux."""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / (1024 * 1024)
    except ImportError:
        # Fallback if psutil is not available
        return 0.0

def generate_synthetic_video(output_path: str, num_frames: int = 10, width: int = 640, height: int = 480) -> None:
    """Generates a synthetic MP4 video with a moving 'person' blob for offline CV testing."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Use MP4V fourcc for cross-platform compatibility
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, 10.0, (width, height))
    
    try:
        for i in range(num_frames):
            # Create a dark gray background frame
            frame = np.ones((height, width, 3), dtype=np.uint8) * 40
            
            # Draw a moving oval blob (simulating a person from a top-down view)
            center_x = int(width * 0.3 + i * (width * 0.4 / num_frames))
            center_y = int(height * 0.4 + i * (height * 0.2 / num_frames))
            
            # Head
            cv2.circle(frame, (center_x, center_y - 20), 15, (220, 220, 220), -1)
            # Body/Shoulders
            cv2.ellipse(frame, (center_x, center_y + 15), (35, 18), 0, 0, 360, (180, 180, 180), -1)
            
            out.write(frame)
    finally:
        out.release()
    print(f"Synthetic test video created at: {output_path}")

def run_test_inference(video_path: str, model_path: str) -> None:
    """Runs YOLOv8 person detection inference on the first 10 frames of a video."""
    print("--- Running YOLOv8 Inference Test ---")
    mem_before = get_memory_usage_mb()
    if mem_before > 0:
        print(f"Initial Memory Usage: {mem_before:.2f} MB")
        
    start_time = time.time()
    
    # Load YOLO model
    model = ModelLoader.get_yolo_model(model_path)
    
    # Open video
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Could not open video file: {video_path}")
        
    frame_count = 0
    total_detections = 0
    confidences = []
    
    try:
        while cap.isOpened() and frame_count < 10:
            ret, frame = cap.read()
            if not ret:
                break
                
            frame_count += 1
            
            # Run inference (classes=[0] for person class in COCO)
            results = model(frame, verbose=False, classes=[0])
            
            detections_in_frame = 0
            frame_confidences = []
            
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    detections_in_frame += 1
                    total_detections += 1
                    conf = float(box.conf[0])
                    confidences.append(conf)
                    frame_confidences.append(conf)
            
            avg_conf = np.mean(frame_confidences) if frame_confidences else 0.0
            print(f"Frame {frame_count:02d}: Detected {detections_in_frame} person(s) | Avg Conf: {avg_conf:.2%}")
            
    finally:
        cap.release()
        
    total_time = time.time() - start_time
    fps = frame_count / total_time if total_time > 0 else 0.0
    mem_after = get_memory_usage_mb()
    
    print("\n--- Results Summary ---")
    if mem_after > 0:
        print(f"Final Memory Usage: {mem_after:.2f} MB (Delta: {mem_after - mem_before:+.2f} MB)")
    print(f"Processed: {frame_count} frames in {total_time:.2f} seconds")
    print(f"Total Detections: {total_detections}")
    print(f"Average Overall Confidence: {np.mean(confidences) if confidences else 0.0:.2%}")
    print(f"Inference test passed: {total_detections} detections in {frame_count} frames, {fps:.2f} fps")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YOLOv8 Inference Test Harness")
    parser.add_argument("video_path", nargs="?", default=None, help="Path to video file")
    parser.add_argument("--model", default="models/yolov8n.pt", help="Path to YOLOv8 model file")
    args = parser.parse_args()
    
    video_file = args.video_path
    if not video_file:
        # Default fallback to synthetic video
        video_file = os.path.join("data", "clips", "test_synthetic.mp4")
        if not os.path.exists(video_file):
            generate_synthetic_video(video_file)
            
    run_test_inference(video_file, args.model)
