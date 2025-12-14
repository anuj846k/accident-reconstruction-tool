"""
Collision Analysis Service.

Analyzes detections to find vehicle collisions based on:
- IoU (Intersection over Union) between bounding boxes
- Distance between vehicle centers
- Temporal persistence of overlaps
"""

import logging
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from collections import defaultdict

import numpy as np

from src.models.detection import Detection

logger = logging.getLogger(__name__)


@dataclass
class CollisionEvent:
    """Represents a detected collision event."""
    track_id_1: int
    track_id_2: int
    first_contact_frame: int
    last_overlap_frame: int
    peak_overlap_frame: int
    max_iou: float
    min_distance: float
    duration_frames: int
    collision_frames: List[int]
    severity: str  # "minor", "moderate", "severe"


@dataclass
class CollisionAnalysisResult:
    """Result of collision analysis."""
    collisions: List[CollisionEvent]
    near_misses: List[Dict[str, Any]]
    total_collisions: int
    total_near_misses: int
    analysis_summary: Dict[str, Any]


def calculate_iou(bbox1: Tuple[float, float, float, float], 
                  bbox2: Tuple[float, float, float, float]) -> float:
    """
    Calculate Intersection over Union (IoU) between two bounding boxes.
    
    Args:
        bbox1: (x, y, w, h) of first bounding box
        bbox2: (x, y, w, h) of second bounding box
        
    Returns:
        IoU value between 0 and 1
    """
    x1, y1, w1, h1 = bbox1
    x2, y2, w2, h2 = bbox2
    
    # Convert to (x1, y1, x2, y2) format
    box1_x1, box1_y1 = x1, y1
    box1_x2, box1_y2 = x1 + w1, y1 + h1
    
    box2_x1, box2_y1 = x2, y2
    box2_x2, box2_y2 = x2 + w2, y2 + h2
    
    # Calculate intersection
    inter_x1 = max(box1_x1, box2_x1)
    inter_y1 = max(box1_y1, box2_y1)
    inter_x2 = min(box1_x2, box2_x2)
    inter_y2 = min(box1_y2, box2_y2)
    
    if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
        return 0.0
    
    inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
    
    # Calculate union
    box1_area = w1 * h1
    box2_area = w2 * h2
    union_area = box1_area + box2_area - inter_area
    
    if union_area == 0:
        return 0.0
    
    return inter_area / union_area


def calculate_distance(center1: Tuple[float, float], 
                       center2: Tuple[float, float]) -> float:
    """Calculate Euclidean distance between two centers."""
    return np.sqrt(
        (center1[0] - center2[0])**2 + 
        (center1[1] - center2[1])**2
    )


def analyze_collisions(
    detections: List[Detection],
    iou_threshold: float = 0.1,
    distance_threshold: float = 50.0,  # pixels
    persistence_frames: int = 3,
    min_collision_frames: int = 2
) -> CollisionAnalysisResult:
    """
    Analyze detections to find vehicle collisions.
    
    Args:
        detections: List of Detection objects
        iou_threshold: Minimum IoU to consider overlap
        distance_threshold: Maximum distance (pixels) to consider close
        persistence_frames: Frames overlap must persist
        min_collision_frames: Minimum frames for collision
        
    Returns:
        CollisionAnalysisResult with detected collisions
    """
    if not detections:
        return CollisionAnalysisResult(
            collisions=[],
            near_misses=[],
            total_collisions=0,
            total_near_misses=0,
            analysis_summary={}
        )
    
    # Group detections by frame
    frames = defaultdict(list)
    for det in detections:
        if det.track_id is not None:
            frames[det.frame_idx].append(det)
    
    # Track pairs and their overlap history
    pair_overlaps = defaultdict(list)  # {(track1, track2): [(frame, iou, distance), ...]}
    
    # Analyze each frame
    for frame_idx in sorted(frames.keys()):
        frame_detections = frames[frame_idx]
        
        # Check all pairs in this frame
        for i, det1 in enumerate(frame_detections):
            for det2 in frame_detections[i+1:]:
                if det1.track_id == det2.track_id:
                    continue
                
                # Calculate IoU
                bbox1 = (det1.bbox_x, det1.bbox_y, det1.bbox_w, det1.bbox_h)
                bbox2 = (det2.bbox_x, det2.bbox_y, det2.bbox_w, det2.bbox_h)
                iou = calculate_iou(bbox1, bbox2)
                
                # Calculate distance
                center1 = (det1.center_x, det1.center_y)
                center2 = (det2.center_x, det2.center_y)
                distance = calculate_distance(center1, center2)
                
                # Check if they overlap or are close
                if iou > iou_threshold or distance < distance_threshold:
                    # Store in sorted order (smaller track_id first)
                    track_pair = tuple(sorted([det1.track_id, det2.track_id]))
                    pair_overlaps[track_pair].append({
                        "frame": frame_idx,
                        "iou": iou,
                        "distance": distance,
                        "det1": det1,
                        "det2": det2
                    })
    
    # Find collisions (persistent overlaps)
    collisions = []
    near_misses = []
    
    for track_pair, overlaps in pair_overlaps.items():
        if len(overlaps) < min_collision_frames:
            continue
        
        # Sort by frame
        overlaps.sort(key=lambda x: x["frame"])
        
        # Find continuous collision segments
        collision_segments = []
        current_segment = [overlaps[0]]
        
        for overlap in overlaps[1:]:
            # Check if gap is small (within persistence_frames)
            gap = overlap["frame"] - current_segment[-1]["frame"]
            if gap <= persistence_frames:
                current_segment.append(overlap)
            else:
                # End current segment, start new one
                if len(current_segment) >= min_collision_frames:
                    collision_segments.append(current_segment)
                current_segment = [overlap]
        
        # Don't forget the last segment
        if len(current_segment) >= min_collision_frames:
            collision_segments.append(current_segment)
        
        # Process each collision segment
        for segment in collision_segments:
            frames_in_segment = [o["frame"] for o in segment]
            ious = [o["iou"] for o in segment]
            distances = [o["distance"] for o in segment]
            
            max_iou = max(ious)
            min_distance = min(distances)
            peak_idx = ious.index(max_iou)
            peak_frame = segment[peak_idx]["frame"]
            
            # Determine severity
            if max_iou > 0.3:
                severity = "severe"
            elif max_iou > 0.15:
                severity = "moderate"
            else:
                severity = "minor"
            
            collision = CollisionEvent(
                track_id_1=track_pair[0],
                track_id_2=track_pair[1],
                first_contact_frame=frames_in_segment[0],
                last_overlap_frame=frames_in_segment[-1],
                peak_overlap_frame=peak_frame,
                max_iou=max_iou,
                min_distance=min_distance,
                duration_frames=len(segment),
                collision_frames=frames_in_segment,
                severity=severity
            )
            
            collisions.append(collision)
        
        # If no collision segments but had overlaps, it's a near-miss
        if not collision_segments and len(overlaps) >= 2:
            min_distance = min(o["distance"] for o in overlaps)
            max_iou = max(o["iou"] for o in overlaps)
            
            near_misses.append({
                "track_id_1": track_pair[0],
                "track_id_2": track_pair[1],
                "closest_frame": min(overlaps, key=lambda x: x["distance"])["frame"],
                "min_distance": min_distance,
                "max_iou": max_iou,
                "total_overlap_frames": len(overlaps)
            })
    
    # Create summary
    analysis_summary = {
        "total_detections": len(detections),
        "total_frames": len(frames),
        "unique_tracks": len(set(d.track_id for d in detections if d.track_id is not None)),
        "collision_pairs": len(set((c.track_id_1, c.track_id_2) for c in collisions)),
        "parameters": {
            "iou_threshold": iou_threshold,
            "distance_threshold": distance_threshold,
            "persistence_frames": persistence_frames,
            "min_collision_frames": min_collision_frames
        }
    }
    
    # Filter to find the most significant collision
    # Priority: EARLIEST collision is usually the actual crash
    # Later collisions are often aftermath (vehicles stuck together)
    if collisions:
        # Sort by EARLIEST first_contact_frame (the actual impact moment)
        # Secondary: higher IoU for tie-breaking
        collisions.sort(
            key=lambda c: (
                c.first_contact_frame,  # Earliest collision first (the actual crash)
                -c.max_iou  # Higher IoU = more significant for tie-breaking
            )
        )
        
        # Filter to significant collisions (IoU > threshold)
        significant_collisions = []
        for collision in collisions:
            # A collision is significant if it has meaningful overlap
            is_significant = collision.max_iou > 0.15 and collision.duration_frames >= 2
            
            if is_significant:
                significant_collisions.append(collision)
                # Keep up to 3 significant collisions
                if len(significant_collisions) >= 3:
                    break
        
        # If we filtered too much, keep at least the earliest collision
        if not significant_collisions and collisions:
            significant_collisions = [collisions[0]]
        
        collisions = significant_collisions
    
    logger.info(
        f"Collision analysis complete: {len(collisions)} significant collisions, "
        f"{len(near_misses)} near-misses found"
    )
    
    return CollisionAnalysisResult(
        collisions=collisions,
        near_misses=near_misses,
        total_collisions=len(collisions),
        total_near_misses=len(near_misses),
        analysis_summary=analysis_summary
    )


def get_key_frames_for_collision(
    detections: List[Detection],
    collision: CollisionEvent,
    padding_frames: int = 5
) -> Dict[str, int]:
    """
    Get key frame indices for a collision event.
    
    Returns:
        Dictionary with frame indices for approach, contact, peak, separation
    """
    frames = sorted(set(d.frame_idx for d in detections))
    
    first_frame = frames[0] if frames else 0
    last_frame = frames[-1] if frames else 0
    
    approach_frame = max(
        first_frame,
        collision.first_contact_frame - padding_frames * 10
    )
    
    contact_frame = collision.first_contact_frame
    peak_frame = collision.peak_overlap_frame
    separation_frame = min(
        last_frame,
        collision.last_overlap_frame + padding_frames * 10
    )
    
    return {
        "approach": approach_frame,
        "contact": contact_frame,
        "peak": peak_frame,
        "separation": separation_frame
    }


def get_track_trajectory(
    detections: List[Detection],
    track_id: int
) -> List[Dict[str, Any]]:
    """
    Get trajectory for a specific track.
    
    Returns:
        List of positions over time
    """
    track_detections = [
        d for d in detections 
        if d.track_id == track_id
    ]
    
    track_detections.sort(key=lambda d: d.frame_idx)
    
    trajectory = []
    for det in track_detections:
        trajectory.append({
            "frame": det.frame_idx,
            "timestamp_ms": det.timestamp_ms,
            "center_x": det.center_x,
            "center_y": det.center_y,
            "bbox": {
                "x": det.bbox_x,
                "y": det.bbox_y,
                "w": det.bbox_w,
                "h": det.bbox_h
            },
            "speed_mph": det.speed_mph,
            "world_x": det.world_x,
            "world_y": det.world_y
        })
    
    return trajectory

