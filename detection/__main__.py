import os
import sys
import argparse

# Allow imports from parent folder
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from detection.test_inference import run_test_inference, generate_synthetic_video

def main():
    parser = argparse.ArgumentParser(description="StoreLens - Computer Vision Pipeline CLI")
    parser.add_argument("video_path", nargs="?", default=None, help="Path to input CCTV video clip")
    parser.add_argument("--model", default="models/yolov8n.pt", help="Path to YOLOv8 model weights file")
    args = parser.parse_args()

    video_file = args.video_path
    if not video_file:
        video_file = os.path.join("data", "clips", "test_synthetic.mp4")
        if not os.path.exists(video_file):
            print("No test video provided or found. Generating synthetic clip...")
            generate_synthetic_video(video_file)

    print(f"Starting pipeline inference on: {video_file}")
    run_test_inference(video_file, args.model)

if __name__ == "__main__":
    main()
