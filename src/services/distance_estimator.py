"""Distance estimation using homography transformation."""

import numpy as np
import cv2
from typing import Tuple, List, Optional
from dataclasses import dataclass
from math import radians, cos, sin, asin, sqrt


@dataclass
class GeoPoint:
    """Geographic point with latitude and longitude."""
    lat: float
    lng: float


class DistanceEstimator:
    """Estimates real-world distances using homography matrix."""
    
    def __init__(self, matrix: List[List[float]]):
        """
        Initialize with pre-computed homography matrix.
        
        Args:
            matrix: 3x3 homography matrix as nested list
        """
        self.homography_matrix = np.array(matrix, dtype=np.float32)
    
    def image_to_geo(self, x_norm: float, y_norm: float) -> GeoPoint:
        """
        Transform normalized image coordinates to GPS.
        
        Args:
            x_norm: Normalized x coordinate (0-1)
            y_norm: Normalized y coordinate (0-1)
            
        Returns:
            GeoPoint with lat/lng
        """
        point = np.array([[x_norm, y_norm]], dtype=np.float32)
        transformed = cv2.perspectiveTransform(
            point.reshape(-1, 1, 2), self.homography_matrix
        )
        lng, lat = transformed[0][0]
        return GeoPoint(lat=float(lat), lng=float(lng))
    
    @staticmethod
    def haversine_distance(point1: GeoPoint, point2: GeoPoint) -> float:
        """
        Calculate great circle distance between two GPS points.
        
        Returns:
            Distance in meters
        """
        R = 6371000  # Earth radius in meters
        
        lat1, lng1 = radians(point1.lat), radians(point1.lng)
        lat2, lng2 = radians(point2.lat), radians(point2.lng)
        
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
        c = 2 * asin(sqrt(a))
        
        return R * c
    
    def estimate_distance(
        self, 
        point1: Tuple[float, float], 
        point2: Tuple[float, float]
    ) -> float:
        """
        Estimate real-world distance between two image points.
        
        Args:
            point1: (x_norm, y_norm) for first point
            point2: (x_norm, y_norm) for second point
            
        Returns:
            Distance in meters
        """
        geo1 = self.image_to_geo(point1[0], point1[1])
        geo2 = self.image_to_geo(point2[0], point2[1])
        return self.haversine_distance(geo1, geo2)
    
    def calculate_speed(
        self,
        point1: Tuple[float, float],
        point2: Tuple[float, float],
        time_diff_seconds: float
    ) -> float:
        """
        Calculate speed between two points.
        
        Returns:
            Speed in mph
        """
        if time_diff_seconds <= 0:
            return 0.0
        
        distance_meters = self.estimate_distance(point1, point2)
        speed_mps = distance_meters / time_diff_seconds
        speed_mph = speed_mps * 2.23694  # Convert m/s to mph
        
        return speed_mph