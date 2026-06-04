import os
import sys
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detection.pipeline import DetectionPipeline

# Path definitions
CCTV_DIR = "data/clips/CCTV Footage"
OUTPUT_EVENTS_PATH = "data/clips/events_real.jsonl"
MODEL_PATH = "models/yolov8n.pt"
STORE_ID = "ST1008"

# 1. Clear previous output file if it exists to ensure fresh run
if os.path.exists(OUTPUT_EVENTS_PATH):
    print(f"Removing old real event logs at: {OUTPUT_EVENTS_PATH}")
    os.remove(OUTPUT_EVENTS_PATH)

# 2. Camera mappings: define base timestamp and camera-specific zones configuration
# We align base timestamps so that events occur on 2026-04-10, matching the POS transaction times
camera_configs = {
    "CAM 1": {
        "camera_id": "CAM1",
        "video_file": "CAM 1.mp4",
        "base_timestamp": datetime(2026, 4, 10, 16, 45, 0),  # Shoppers enter store
        "zones_config": {
            "ST1008": {
                "frame_width": 1920,
                "frame_height": 1080,
                "entry_line": [[0.0, 0.8], [1.0, 0.8]],  # Detect entries/exits
                "zones": {}  # Entry camera has no shelf zones
            }
        }
    },
    "CAM 2": {
        "camera_id": "CAM2",
        "video_file": "CAM 2.mp4",
        "base_timestamp": datetime(2026, 4, 10, 16, 47, 0),  # Shoppers visit Skin care
        "zones_config": {
            "ST1008": {
                "frame_width": 1920,
                "frame_height": 1080,
                "entry_line": [[0.0, 0.0], [0.0, 0.0]],
                "zones": {
                    "skin": {
                        "type": "polygon",
                        "points": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]  # Cover entire frame for reliability
                    }
                }
            }
        }
    },
    "CAM 3": {
        "camera_id": "CAM3",
        "video_file": "CAM 3.mp4",
        "base_timestamp": datetime(2026, 4, 10, 16, 48, 0),  # Shoppers visit Makeup Unit
        "zones_config": {
            "ST1008": {
                "frame_width": 1920,
                "frame_height": 1080,
                "entry_line": [[0.0, 0.0], [0.0, 0.0]],
                "zones": {
                    "makeup": {
                        "type": "polygon",
                        "points": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
                    }
                }
            }
        }
    },
    "CAM 4": {
        "camera_id": "CAM4",
        "video_file": "CAM 4.mp4",
        "base_timestamp": datetime(2026, 4, 10, 16, 49, 0),  # Shoppers visit Bath & Body
        "zones_config": {
            "ST1008": {
                "frame_width": 1920,
                "frame_height": 1080,
                "entry_line": [[0.0, 0.0], [0.0, 0.0]],
                "zones": {
                    "bath-and-body": {
                        "type": "polygon",
                        "points": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
                    }
                }
            }
        }
    },
    "CAM 5": {
        "camera_id": "CAM5",
        "video_file": "CAM 5.mp4",
        "base_timestamp": datetime(2026, 4, 10, 16, 52, 0),  # Shoppers join Billing Queue (Invoice ML0426KAP0001358 is at 16:55:36)
        "zones_config": {
            "ST1008": {
                "frame_width": 1920,
                "frame_height": 1080,
                "entry_line": [[0.0, 0.0], [0.0, 0.0]],
                "zones": {
                    "BILLING": {
                        "type": "polygon",
                        "points": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
                    }
                }
            }
        }
    }
}

def main():
    print("=========================================")
    print("   Starting Retail Video CV Pipeline     ")
    print("=========================================")
    
    for cam_name, config in sorted(camera_configs.items()):
        video_path = os.path.join(CCTV_DIR, config["video_file"])
        if not os.path.exists(video_path):
            print(f"Error: Video file missing at {video_path}")
            continue
            
        print(f"\n---> Processing {cam_name} (File: {config['video_file']})")
        print(f"     Camera ID: {config['camera_id']} | Base Timestamp: {config['base_timestamp']}")
        
        # Initialize pipeline for this camera
        pipeline = DetectionPipeline(
            model_path=MODEL_PATH,
            store_id=STORE_ID,
            camera_id=config["camera_id"],
            zones_config=config["zones_config"],
            output_path=OUTPUT_EVENTS_PATH
        )
        
        # Run processing sequentially with a 600 frames limit for high-speed execution
        pipeline.process_clip(video_path, base_timestamp=config["base_timestamp"], max_frames=600)
        
    print("\n=========================================")
    print(f"CV Processing complete. Real events written to {OUTPUT_EVENTS_PATH}")
    print("=========================================")

if __name__ == "__main__":
    main()
