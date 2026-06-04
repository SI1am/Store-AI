import os
import pytest
import numpy as np
from datetime import datetime, timedelta

from detection.tracker import PersonTracker, calculate_iou
from detection.event_emitter import EventEmitter
from detection.zone_mapper import ZoneMapper
from detection.staff_classifier import StaffClassifier
from detection.reid import ReIDEngine
from detection.group_detector import GroupDetector
from detection.staff_classifier_enhanced import EnhancedStaffClassifier

def test_calculate_iou():
    box1 = [10, 10, 50, 50]
    box2 = [20, 20, 60, 60]
    # Intersection: [20, 20, 50, 50] -> area = 30 * 30 = 900
    # Box1 area = 40 * 40 = 1600
    # Box2 area = 40 * 40 = 1600
    # Union = 1600 + 1600 - 900 = 2300
    # IoU = 900 / 2300 = 0.3913
    assert abs(calculate_iou(box1, box2) - 0.3913) < 0.001

def test_person_tracking():
    tracker = PersonTracker(conf_high=0.5, conf_low=0.1)
    
    # Frame 1: Shopper appears
    dets_f1 = [{'xyxy': [100, 100, 150, 200], 'confidence': 0.8, 'center': (125, 150)}]
    tracks_f1 = tracker.update(dets_f1)
    assert len(tracks_f1) == 1
    assert tracks_f1[0]['track_id'] == 1
    assert tracks_f1[0]['is_confirmed'] is False  # Seen for only 1 frame
    
    # Frame 2: Shopper moves slightly (IoU matches)
    dets_f2 = [{'xyxy': [105, 102, 152, 202], 'confidence': 0.82, 'center': (128, 152)}]
    tracks_f2 = tracker.update(dets_f2)
    assert len(tracks_f2) == 1
    assert tracks_f2[0]['track_id'] == 1
    
    # Frame 3: Shopper goes behind a pole (occluded)
    tracks_f3 = tracker.update([])
    assert len(tracks_f3) == 0  # No active tracks on screen
    assert 1 in tracker.occluded_tracks  # But preserved in occlusion buffer
    
    # Frame 4: Shopper emerges (re-associated)
    dets_f4 = [{'xyxy': [107, 103, 155, 205], 'confidence': 0.79, 'center': (131, 154)}]
    tracks_f4 = tracker.update(dets_f4)
    assert len(tracks_f4) == 1
    assert tracks_f4[0]['track_id'] == 1

def test_line_crossing():
    # Vertical line going down from x=50, y=0 to x=50, y=100
    line = [(50, 0), (50, 100)]
    
    # Case 1: Cross left-to-right (ENTRY)
    p_prev = (40, 50)
    p_curr = (60, 50)
    direction = EventEmitter.get_line_crossing_direction(p_prev, p_curr, line)
    assert direction == "ENTRY"
    
    # Case 2: Cross right-to-left (EXIT)
    p_prev = (60, 50)
    p_curr = (40, 50)
    direction = EventEmitter.get_line_crossing_direction(p_prev, p_curr, line)
    assert direction == "EXIT"
    
    # Case 3: No cross
    p_prev = (40, 50)
    p_curr = (45, 50)
    direction = EventEmitter.get_line_crossing_direction(p_prev, p_curr, line)
    assert direction is None

def test_zone_mapper(sample_zones_config):
    mapper = ZoneMapper(sample_zones_config, "S001")
    
    # Test point completely inside PRODUCT_A zone (polygon bounds: 0 to 256 x, 0 to 240 y in pixel scaling)
    # Scaled PRODUCT_A: [0, 0] to [256, 240]
    inside_x = 100
    inside_y = 100
    zones = mapper.get_point_in_zones(inside_x, inside_y)
    assert "PRODUCT_A" in zones
    assert "BILLING" not in zones

    # Test point outside all zones
    outside_x = 500
    outside_y = 100
    zones = mapper.get_point_in_zones(outside_x, outside_y)
    assert len(zones) == 0

def test_staff_classifier():
    classifier = StaffClassifier()
    # Disable DL loading during tests to prevent random weight predictions
    classifier.tried_loading = True
    classifier._model = None
    
    # Heuristics check: Shopper in top 20% (y_pct < 0.2) seen > 10 frames -> Staff
    patch = np.ones((50, 50, 3), dtype=np.uint8) * 100
    res = classifier.classify(patch, y_center_pct=0.15, frame_count=12)
    assert res['is_staff'] is True
    assert res['reasoning'] == 'spatial_heuristic_top_frame_desk'

    # Heuristics check: Shopper in normal region -> Customer (DL fallback defaults to False)
    res = classifier.classify(patch, y_center_pct=0.5, frame_count=5)
    assert res['is_staff'] is False

def test_reentry_checks():
    reid = ReIDEngine()
    token = reid.generate_reid_token(track_id=45)
    base_time = datetime.utcnow()
    
    # Visitor exits
    reid.store_session(token, base_time)
    assert reid.get_session_number(token) == 1
    
    # Re-enters 2 minutes later (should trigger reentry)
    assert reid.check_reentry(token, base_time + timedelta(minutes=2)) is True
    
    # Re-enters 6 minutes later (should not trigger reentry, treated as new visit)
    assert reid.check_reentry(token, base_time + timedelta(minutes=6)) is False

def test_group_detection():
    # Entry line coordinates
    line = [(0.0, 0.8), (1.0, 0.8)]
    detector = GroupDetector(line, frame_height=480)
    
    # Frame 10: two shoppers cross entry line simultaneously
    crossings = [
        {'track_id': 101, 'confidence': 0.92},
        {'track_id': 102, 'confidence': 0.87}
    ]
    groups = detector.detect_group_crossings(crossings, frame_idx=10)
    
    assert len(groups) == 1
    assert groups[0]['num_people'] == 2
    assert 101 in groups[0]['track_ids']
    assert groups[0]['confidence'] == 0.895

def test_enhanced_staff_classifier():
    classifier = EnhancedStaffClassifier()

    # Create dummy black outfit patch (V < 50, low saturation)
    # HSV: Hue=0, Sat=10, Val=30 -> RGB roughly (30, 30, 30) (black)
    black_patch = np.ones((50, 50, 3), dtype=np.uint8) * 30

    # Create dummy color outfit patch
    # RGB roughly (200, 100, 100) (colored)
    color_patch = np.ones((50, 50, 3), dtype=np.uint8)
    color_patch[:, :, 0] = 100
    color_patch[:, :, 1] = 100
    color_patch[:, :, 2] = 200

    # Test 1: Staff in black at cash counter -> is_staff=True
    # Spatial: y=100 (y_pct = 100/1080 = 0.09 < 0.25)
    # Frequency: frame_count = 110 (110/100 = 1.0)
    # Outfit: black_patch (darkness > 0.7)
    # Stationarity: displacement = 1.0 (very low)
    staff_track_data = {
        "y_center": 100,
        "frame_count": 110,
        "trajectory": [(400, 100), (401, 100), (400, 100)],
        "active_zones": ["BILLING"]
    }
    res1 = classifier.classify(black_patch, staff_track_data, frame_height=1080.0, frame_width=1920.0)
    assert res1.is_staff is True

    # Test 2: Customer in black browsing shelf -> is_staff=False
    # Spatial: y=600 (y_pct = 600/1080 = 0.55 > 0.25)
    # Frequency: frame_count = 50
    # Outfit: black_patch
    # Stationarity: displacement = 15.0 (high movement)
    customer_black_track_data = {
        "y_center": 600,
        "frame_count": 50,
        "trajectory": [(200, 600), (215, 600), (230, 600)],
        "active_zones": ["skin"]
    }
    res2 = classifier.classify(black_patch, customer_black_track_data, frame_height=1080.0, frame_width=1920.0)
    assert res2.is_staff is False

    # Test 3: Staff helping customer (mixed) -> is_staff=True (spatial wins)
    # Spatial: y=150 (y_pct = 150/1080 = 0.13 < 0.25)
    # Outfit: black_patch
    # Stationarity: displacement = 5.0 (moderate movement)
    mixed_track_data = {
        "y_center": 150,
        "frame_count": 105,
        "trajectory": [(400, 150), (405, 150), (410, 150)],
        "active_zones": ["BILLING"]
    }
    res3 = classifier.classify(black_patch, mixed_track_data, frame_height=1080.0, frame_width=1920.0)
    assert res3.is_staff is True

    # Test 4: Tall customer in top frame with black outfit -> is_staff=False (movement wins)
    # Spatial: y=200 (y_pct = 0.18 < 0.25)
    # Outfit: black_patch
    # Stationarity: displacement = 14.0 (high movement)
    tall_customer_track_data = {
        "y_center": 200,
        "frame_count": 80,
        "trajectory": [(300, 200), (314, 200), (328, 200)],
        "active_zones": ["skin"]
    }
    res4 = classifier.classify(black_patch, tall_customer_track_data, frame_height=1080.0, frame_width=1920.0)
    assert res4.is_staff is False

    # Test 5: Customer in color outfit stationary at cash counter -> is_staff=False (non-black uniform wins)
    # Spatial: y=100 (y_pct < 0.25)
    # Outfit: color_patch (darkness < 0.3)
    # Stationarity: displacement = 1.0 (very stationary)
    customer_color_track_data = {
        "y_center": 100,
        "frame_count": 110,
        "trajectory": [(400, 100), (401, 100), (400, 100)],
        "active_zones": ["BILLING"]
    }
    res5 = classifier.classify(color_patch, customer_color_track_data, frame_height=1080.0, frame_width=1920.0)
    assert res5.is_staff is False

