import logging
import cv2
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class StaffClassificationResult(BaseModel):
    is_staff: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: Dict[str, float]

class EnhancedStaffClassifier:
    def __init__(self, cash_counter_zone: str = "BILLING", threshold_score: float = 0.6):
        self.cash_counter_zone = cash_counter_zone
        self.threshold_score = threshold_score

    def calculate_darkness(self, patch: np.ndarray) -> float:
        """
        Extracts darkness ratio using HSV space analysis.
        If V (Value/Brightness) < 50 and Saturation is low, it counts as black outfit pixels.
        Returns ratio of black pixels to total pixels (0.0 to 1.0).
        """
        if patch is None or patch.size == 0:
            return 0.0

        try:
            # Convert BGR to HSV
            hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
            
            # S channel (index 1), V channel (index 2)
            s_channel = hsv[:, :, 1]
            v_channel = hsv[:, :, 2]
            
            # Count dark pixels (V < 50) with low saturation (S < 80 to represent black/gray uniforms)
            dark_mask = (v_channel < 50) & (s_channel < 80)
            dark_pixels = np.sum(dark_mask)
            total_pixels = patch.shape[0] * patch.shape[1]
            
            darkness_ratio = float(dark_pixels / total_pixels) if total_pixels > 0 else 0.0
            return darkness_ratio
        except Exception as e:
            logger.warning(f"Darkness calculation failed: {e}")
            return 0.0

    def calculate_displacement(self, trajectory: List[Tuple[float, float]]) -> float:
        """
        Calculates average step-by-step displacement in pixels.
        High displacement indicates moving/browsing customers.
        Low displacement indicates stationary cashiers.
        """
        if not trajectory or len(trajectory) < 2:
            return 0.0

        displacements = []
        for i in range(1, len(trajectory)):
            p1 = trajectory[i - 1]
            p2 = trajectory[i]
            dist = np.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)
            displacements.append(dist)

        return float(np.mean(displacements)) if displacements else 0.0

    def classify(
        self,
        patch: np.ndarray,
        track_data: Dict[str, Any],
        frame_height: float,
        frame_width: float,
        total_clip_frames: int = 600
    ) -> StaffClassificationResult:
        """
        Classifies whether a person track is staff or customer based on an ensemble scoring logic:
        - Spatial counters (40%): y_center_pct < 0.25 (cash counter region)
        - Frequency (25%): appearance frequency relative to clip length
        - Black outfit (15%): HSV darkness ratio check
        - Stationarity (15%): inverse displacement check
        - Zone preference (5%): percent of trajectory spent in BILLING zone
        """
        scores = {
            "spatial": 0.0,
            "frequency": 0.0,
            "black_outfit": 0.0,
            "stationary": 0.0,
            "zone_preference": 0.0
        }

        # 1. Spatial proximity to cash counter
        y_center = track_data.get("y_center")
        if y_center is None and "trajectory" in track_data and track_data["trajectory"]:
            y_center = track_data["trajectory"][-1][1]
        
        active_zones = track_data.get("active_zones", [])
        is_near_billing = (self.cash_counter_zone in active_zones)
        
        if y_center is not None:
            y_center_pct = y_center / frame_height
            scores["spatial"] = 1.0 if (y_center_pct < 0.25 or is_near_billing) else 0.0
        elif is_near_billing:
            scores["spatial"] = 1.0

        # 2. Appearance frequency
        frame_count = track_data.get("frame_count", 1)
        scores["frequency"] = min(frame_count / 100.0, 1.0)

        # 3. Black outfit detection via HSV color analysis
        scores["black_outfit"] = self.calculate_darkness(patch)

        # 4. Stationarity (movement analysis)
        trajectory = track_data.get("trajectory", [])
        avg_displacement = self.calculate_displacement(trajectory)
        # Standardize displacement: displacement under 4px is considered fully stationary
        if len(trajectory) < 2:
            scores["stationary"] = 1.0
        else:
            scores["stationary"] = max(0.0, 1.0 - (avg_displacement / 12.0))

        # 5. Zone preference
        active_zones = track_data.get("active_zones", [])
        if self.cash_counter_zone in active_zones:
            scores["zone_preference"] = 1.0

        # Weighted sum ensemble
        staff_score = (
            0.40 * scores["spatial"] +
            0.25 * scores["frequency"] +
            0.15 * scores["black_outfit"] +
            0.15 * scores["stationary"] +
            0.05 * scores["zone_preference"]
        )

        # CRITICAL PENALTY: Shopper wears a black outfit but moves around (customer shopping behavior)
        if scores["black_outfit"] > 0.7 and scores["stationary"] < 0.3:
            staff_score *= 0.4

        # CRITICAL PENALTY: Shopper is not wearing a black uniform (non-black outfit)
        if scores["black_outfit"] < 0.35:
            staff_score *= 0.2

        # Final decision
        is_staff = staff_score > self.threshold_score
        
        return StaffClassificationResult(
            is_staff=is_staff,
            confidence=round(staff_score, 4),
            reasoning=scores
        )
