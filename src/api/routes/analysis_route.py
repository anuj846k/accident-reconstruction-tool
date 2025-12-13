"""
Collision Analysis API routes.

Handles:
- Analyzing detections to find collisions
- Getting collision details
- Getting vehicle trajectories
"""

import uuid
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.api.deps import get_db, get_current_user
from src.models.user import User
from src.models.project import Project
from src.models.detection import Detection
from src.services import processing as processing_service
from src.services.collision_analysis import (
    analyze_collisions,
    get_key_frames_for_collision,
    CollisionEvent
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analysis", tags=["analysis"])


# ============== Request/Response Schemas ==============

class CollisionResponse(BaseModel):
    """Single collision event response."""
    track_id_1: int
    track_id_2: int
    first_contact_frame: int
    last_overlap_frame: int
    peak_overlap_frame: int
    max_iou: float
    min_distance: float
    duration_frames: int
    collision_frames: List[int]
    severity: str
    key_frames: dict  # {"approach": int, "contact": int, "peak": int, "separation": int}


class CollisionsListResponse(BaseModel):
    """List of collisions response."""
    project_id: uuid.UUID
    collisions: List[CollisionResponse]
    near_misses: List[dict]
    total_collisions: int
    total_near_misses: int
    analysis_summary: dict


class TrajectoryPoint(BaseModel):
    """Single point in vehicle trajectory."""
    frame_idx: int
    timestamp_ms: int
    center_x: float
    center_y: float
    bbox_x: float
    bbox_y: float
    bbox_w: float
    bbox_h: float
    confidence: float


class TrajectoryResponse(BaseModel):
    """Vehicle trajectory response."""
    track_id: int
    project_id: uuid.UUID
    trajectory: List[TrajectoryPoint]
    total_points: int


# ============== API Endpoints ==============

@router.get("/project/{project_id}/collisions", response_model=CollisionsListResponse)
async def get_project_collisions(
    project_id: uuid.UUID,
    iou_threshold: float = Query(0.1, description="Minimum IoU for collision"),
    distance_threshold: float = Query(50.0, description="Maximum distance in pixels"),
    persistence_frames: int = Query(3, description="Frames overlap must persist"),
    min_collision_frames: int = Query(2, description="Minimum frames for collision"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Analyze detections to find collisions in a project.
    
    Automatically returns the collision with the highest IoU (most significant collision).
    This helps filter out false positives from track fragmentation.
    """
    # Check authorization
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get all detections for the project
    detections = await processing_service.get_all_detections(db, project_id, limit=100000)
    
    if not detections:
        return CollisionsListResponse(
            project_id=project_id,
            collisions=[],
            near_misses=[],
            total_collisions=0,
            total_near_misses=0,
            analysis_summary={
                "total_detections": 0,
                "total_frames": 0,
                "unique_tracks": 0,
                "parameters": {
                    "iou_threshold": iou_threshold,
                    "distance_threshold": distance_threshold,
                    "persistence_frames": persistence_frames,
                    "min_collision_frames": min_collision_frames
                }
            }
        )
    
    # Run collision analysis
    analysis_result = analyze_collisions(
        detections,
        iou_threshold=iou_threshold,
        distance_threshold=distance_threshold,
        persistence_frames=persistence_frames,
        min_collision_frames=min_collision_frames
    )
    
    # Filter to the collision with highest IoU (most significant)
    # This helps eliminate false positives from track fragmentation
    collisions_to_process = analysis_result.collisions
    if collisions_to_process:
        # Sort by max_iou descending, then by duration (longer = more significant)
        collisions_to_process = sorted(
            collisions_to_process,
            key=lambda c: (-c.max_iou, -c.duration_frames)
        )
        # Take only the top collision (highest IoU)
        collisions_to_process = [collisions_to_process[0]]
        logger.info(
            f"Auto-selected top collision: Track {collisions_to_process[0].track_id_1} vs "
            f"Track {collisions_to_process[0].track_id_2}, IoU={collisions_to_process[0].max_iou:.3f}"
        )
    
    # Convert collisions to response format
    collision_responses = []
    for collision in collisions_to_process:
        # Get key frames for this collision
        key_frames = get_key_frames_for_collision(
            detections,
            collision
        )
        
        collision_responses.append(CollisionResponse(
            track_id_1=collision.track_id_1,
            track_id_2=collision.track_id_2,
            first_contact_frame=collision.first_contact_frame,
            last_overlap_frame=collision.last_overlap_frame,
            peak_overlap_frame=collision.peak_overlap_frame,
            max_iou=collision.max_iou,
            min_distance=collision.min_distance,
            duration_frames=collision.duration_frames,
            collision_frames=collision.collision_frames,
            severity=collision.severity,
            key_frames=key_frames
        ))
    
    # Get unique tracks count
    unique_tracks = len(set(d.track_id for d in detections if d.track_id is not None))
    total_frames = len(set(d.frame_idx for d in detections))
    
    return CollisionsListResponse(
        project_id=project_id,
        collisions=collision_responses,
        near_misses=analysis_result.near_misses,
        total_collisions=len(collision_responses),  # Return count of filtered collisions
        total_near_misses=analysis_result.total_near_misses,
        analysis_summary={
            "total_detections": len(detections),
            "total_frames": total_frames,
            "unique_tracks": unique_tracks,
            "total_collisions_detected": analysis_result.total_collisions,  # Original count before filtering
            "collisions_filtered": True,  # Indicate that filtering was applied
            "parameters": {
                "iou_threshold": iou_threshold,
                "distance_threshold": distance_threshold,
                "persistence_frames": persistence_frames,
                "min_collision_frames": min_collision_frames
            }
        }
    )


@router.get("/project/{project_id}/track/{track_id}/trajectory", response_model=TrajectoryResponse)
async def get_track_trajectory(
    project_id: uuid.UUID,
    track_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get trajectory (all positions) for a specific vehicle track."""
    # Check authorization
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get all detections for this track
    detections = await processing_service.get_detections_by_track(db, project_id, track_id)
    
    if not detections:
        raise HTTPException(
            status_code=404,
            detail=f"Track {track_id} not found for project {project_id}"
        )
    
    # Convert to trajectory points
    trajectory = [
        TrajectoryPoint(
            frame_idx=d.frame_idx,
            timestamp_ms=d.timestamp_ms,
            center_x=d.center_x,
            center_y=d.center_y,
            bbox_x=d.bbox_x,
            bbox_y=d.bbox_y,
            bbox_w=d.bbox_w,
            bbox_h=d.bbox_h,
            confidence=d.confidence
        )
        for d in sorted(detections, key=lambda x: (x.frame_idx, x.timestamp_ms))
    ]
    
    return TrajectoryResponse(
        track_id=track_id,
        project_id=project_id,
        trajectory=trajectory,
        total_points=len(trajectory)
    )

