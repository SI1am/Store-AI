import logging
from typing import Dict, Any, List, Tuple
from shapely.geometry import Point, Polygon

logger = logging.getLogger(__name__)

class ZoneMapper:
    def __init__(self, zones_config: Dict[str, Any], store_id: str):
        self.store_id = store_id
        self.zones: Dict[str, Polygon] = {}
        
        # Load and validate configuration
        store_config = zones_config.get(store_id)
        if not store_config:
            raise ValueError(f"Store config not found for store_id: {store_id}")
            
        self.frame_width = store_config.get("frame_width", 1920)
        self.frame_height = store_config.get("frame_height", 1080)
        
        raw_zones = store_config.get("zones", {})
        for zone_id, zone_data in raw_zones.items():
            points = zone_data.get("points", [])
            if len(points) < 3:
                raise ValueError(f"Zone '{zone_id}' polygon must have at least 3 points. Found {len(points)}")
                
            # Convert normalized 0-1 coordinates to pixel coordinates
            pixel_points = []
            for p in points:
                px = p[0] * self.frame_width
                py = p[1] * self.frame_height
                pixel_points.append((px, py))
                
            # Create Shapely Polygon
            self.zones[zone_id] = Polygon(pixel_points)
            logger.info(f"Loaded zone '{zone_id}' with {len(pixel_points)} coordinates.")

    def get_point_in_zones(self, x: float, y: float) -> List[str]:
        """
        Determines which zones contain the pixel coordinates (x, y).
        Returns a list of matching zone IDs.
        """
        point = Point(x, y)
        matching_zones = []
        
        for zone_id, polygon in self.zones.items():
            # contains() handles containment, while touches() or intersects() handles boundary cases
            # We check if polygon contains point. If it lies exactly on the boundary, we include it as well
            if polygon.contains(point) or polygon.touches(point):
                matching_zones.append(zone_id)
                
        return matching_zones

    def get_zone_polygon(self, zone_id: str) -> Polygon:
        """Returns the Shapely Polygon object for the specified zone."""
        if zone_id not in self.zones:
            raise KeyError(f"Zone ID '{zone_id}' not found.")
        return self.zones[zone_id]
