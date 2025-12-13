"""Homography matrix calculation using OpenCV."""

import numpy as np
import cv2
from typing import List, Tuple
from dataclasses import dataclass


@dataclass
class HomographyResult:
    """Result of homography calculation."""
    matrix: List[List[float]]
    reprojection_error: float
    inlier_count: int
    status: str


def solve_homography_from_pairs(pairs) -> HomographyResult:
    """
    Calculate homography matrix from point pairs using OpenCV RANSAC.
    
    Args:
        pairs: List of HomographyPair ORM objects
        
    Returns:
        HomographyResult with 3x3 matrix
    """
    if len(pairs) < 4:
        raise ValueError("At least 4 point pairs required for homography")
    
    # Extract source (image) and destination (GPS) points
    src_points = []
    dst_points = []
    
    for pair in pairs:
        src_points.append([pair.image_x_norm, pair.image_y_norm])
        dst_points.append([pair.map_lng, pair.map_lat])  # lng=x, lat=y
    
    src_points = np.array(src_points, dtype=np.float32)
    dst_points = np.array(dst_points, dtype=np.float32)
    
    # Calculate homography with RANSAC
    homography_matrix, mask = cv2.findHomography(
        src_points, dst_points, cv2.RANSAC, 5.0
    )
    
    if homography_matrix is None:
        raise ValueError("Failed to calculate homography matrix")
    
    # Calculate reprojection error
    reprojection_error = _calculate_reprojection_error(
        src_points, dst_points, homography_matrix, mask
    )
    
    inlier_count = int(np.sum(mask)) if mask is not None else len(pairs)
    
    return HomographyResult(
        matrix=homography_matrix.tolist(),
        reprojection_error=reprojection_error,
        inlier_count=inlier_count,
        status="success"
    )


def _calculate_reprojection_error(
    src_points: np.ndarray,
    dst_points: np.ndarray,
    homography_matrix: np.ndarray,
    mask: np.ndarray
) -> float:
    """Calculate mean reprojection error for inlier points."""
    if mask is None:
        mask = np.ones(len(src_points), dtype=bool)
    
    src_homogeneous = np.hstack([src_points, np.ones((len(src_points), 1))])
    transformed = src_homogeneous @ homography_matrix.T
    transformed_2d = transformed[:, :2] / transformed[:, 2:3]
    
    inlier_indices = np.where(mask)[0]
    if len(inlier_indices) == 0:
        return float('inf')
    
    errors = np.linalg.norm(
        transformed_2d[inlier_indices] - dst_points[inlier_indices], 
        axis=1
    )
    return float(np.mean(errors))


def transform_point(
    x_norm: float, 
    y_norm: float, 
    matrix: List[List[float]]
) -> Tuple[float, float]:
    """Transform normalized image point to GPS coordinates."""
    matrix_np = np.array(matrix, dtype=np.float32)
    point = np.array([[x_norm, y_norm]], dtype=np.float32)
    
    transformed = cv2.perspectiveTransform(
        point.reshape(-1, 1, 2), matrix_np
    )
    
    lng, lat = transformed[0][0]
    return float(lng), float(lat)