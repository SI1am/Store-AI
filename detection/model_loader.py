import os
import logging
from typing import Optional
from ultralytics import YOLO

logger = logging.getLogger(__name__)

class ModelLoader:
    _yolo_model: Optional[YOLO] = None

    @classmethod
    def get_yolo_model(cls, model_path: str = "models/yolov8n.pt") -> YOLO:
        """
        Lazy-loads the YOLOv8 model. If the model is not present locally,
        it will be downloaded and saved to the specified path.
        """
        if cls._yolo_model is not None:
            return cls._yolo_model

        # Ensure target models directory exists
        model_dir = os.path.dirname(model_path)
        if model_dir and not os.path.exists(model_dir):
            os.makedirs(model_dir, exist_ok=True)

        logger.info(f"Loading YOLOv8 model from {model_path}...")
        try:
            # YOLO(path) handles automatic download if it's a standard name like 'yolov8n.pt'
            # and not present at the given path.
            model = YOLO(model_path)
            cls._yolo_model = model
            logger.info("YOLOv8 model successfully loaded and cached.")
            return cls._yolo_model
        except Exception as e:
            error_msg = f"Failed to load/download YOLOv8 model at {model_path}: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
