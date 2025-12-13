"""
Processing Service - CRUD operations for ProcessingRun and Detection models.
"""

import uuid
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.detection import Detection, ProcessingRun
from src.services.video_processor import DetectionResult

logger = logging.getLogger(__name__)


# ============== Pydantic Schemas ==============

class ProcessingRunCreate(BaseModel):
    """Schema for creating a processing run."""
    project_id: uuid.UUID
    video_uri: str
    config: Optional[dict] = None


class ProcessingRunPublic(BaseModel):
    """Public schema for processing run."""
    id: uuid.UUID
    project_id: uuid.UUID
    status: str
    video_uri: str
    total_frames: Optional[int]
    processed_frames: Optional[int]
    detection_count: Optional[int]
    unique_tracks: Optional[int]
    config: Optional[dict]
    error_message: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class ProcessingStats(BaseModel):
    """Processing statistics for a project."""
    total_runs: int
    completed_runs: int
    failed_runs: int
    total_detections: int
    unique_tracks: int
    total_frames_processed: int


# ============== CRUD Functions ==============

async def create_processing_run(
    db: AsyncSession,
    run_data: ProcessingRunCreate
) -> ProcessingRun:
    """Create a new processing run."""
    run = ProcessingRun(
        project_id=run_data.project_id,
        status="pending",
        video_uri=run_data.video_uri,
        config=run_data.config,
        started_at=datetime.utcnow(),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def get_processing_run(
    db: AsyncSession,
    run_id: uuid.UUID
) -> Optional[ProcessingRun]:
    """Get a processing run by ID."""
    result = await db.execute(
        select(ProcessingRun).where(ProcessingRun.id == run_id)
    )
    return result.scalar_one_or_none()


async def update_processing_run_status(
    db: AsyncSession,
    run_id: uuid.UUID,
    status: str,
    total_frames: Optional[int] = None,
    processed_frames: Optional[int] = None,
    detection_count: Optional[int] = None,
    unique_tracks: Optional[int] = None,
    error_message: Optional[str] = None
) -> Optional[ProcessingRun]:
    """Update processing run status and statistics."""
    run = await get_processing_run(db, run_id)
    if not run:
        return None
    
    run.status = status
    
    if total_frames is not None:
        run.total_frames = total_frames
    if processed_frames is not None:
        run.processed_frames = processed_frames
    if detection_count is not None:
        run.detection_count = detection_count
    if unique_tracks is not None:
        run.unique_tracks = unique_tracks
    if error_message is not None:
        run.error_message = error_message
    
    if status == "processing" and not run.started_at:
        run.started_at = datetime.utcnow()
    elif status in ["completed", "failed"]:
        run.completed_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(run)
    return run


async def list_processing_runs(
    db: AsyncSession,
    project_id: uuid.UUID
) -> List[ProcessingRunPublic]:
    """List all processing runs for a project."""
    result = await db.execute(
        select(ProcessingRun)
        .where(ProcessingRun.project_id == project_id)
        .order_by(ProcessingRun.created_at.desc())
    )
    runs = result.scalars().all()
    return [ProcessingRunPublic.model_validate(run) for run in runs]


async def save_detections(
    db: AsyncSession,
    project_id: uuid.UUID,
    detections: List[DetectionResult]
) -> int:
    """
    Save detection results to database.
    
    Includes speed and world coordinates if available from homography calibration.
    """
    if not detections:
        return 0
    
    detection_objects = []
    for det in detections:
        detection = Detection(
            project_id=project_id,
            frame_idx=det.frame_idx,
            timestamp_ms=det.timestamp_ms,
            track_id=det.track_id,
            class_name=det.class_name,
            class_id=det.class_id,
            confidence=det.confidence,
            bbox_x=det.bbox_x,
            bbox_y=det.bbox_y,
            bbox_w=det.bbox_w,
            bbox_h=det.bbox_h,
            center_x=det.center_x,
            center_y=det.center_y,
            # Calibration-based fields (populated when homography is available)
            speed_mph=det.speed_mph,
            world_x=det.world_x,
            world_y=det.world_y,
        )
        detection_objects.append(detection)
    
    db.add_all(detection_objects)
    await db.commit()
    
    # Log statistics
    speed_count = sum(1 for d in detections if d.speed_mph is not None)
    logger.info(f"Saved {len(detection_objects)} detections ({speed_count} with speed data)")
    
    return len(detection_objects)


async def get_all_detections(
    db: AsyncSession,
    project_id: uuid.UUID,
    limit: int = 1000
) -> List[Detection]:
    """Get all detections for a project."""
    result = await db.execute(
        select(Detection)
        .where(Detection.project_id == project_id)
        .order_by(Detection.frame_idx, Detection.timestamp_ms)
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_detections_by_frame(
    db: AsyncSession,
    project_id: uuid.UUID,
    frame_idx: int
) -> List[Detection]:
    """Get detections for a specific frame."""
    result = await db.execute(
        select(Detection)
        .where(Detection.project_id == project_id)
        .where(Detection.frame_idx == frame_idx)
        .order_by(Detection.timestamp_ms)
    )
    return list(result.scalars().all())


async def get_detections_by_track(
    db: AsyncSession,
    project_id: uuid.UUID,
    track_id: int
) -> List[Detection]:
    """Get all detections for a specific track."""
    result = await db.execute(
        select(Detection)
        .where(Detection.project_id == project_id)
        .where(Detection.track_id == track_id)
        .order_by(Detection.frame_idx, Detection.timestamp_ms)
    )
    return list(result.scalars().all())


async def get_unique_tracks(
    db: AsyncSession,
    project_id: uuid.UUID
) -> List[int]:
    """Get list of unique track IDs for a project."""
    result = await db.execute(
        select(Detection.track_id)
        .where(Detection.project_id == project_id)
        .where(Detection.track_id.isnot(None))
        .distinct()
        .order_by(Detection.track_id)
    )
    track_ids = [row[0] for row in result.all()]
    return sorted(track_ids)


async def get_processing_stats(
    db: AsyncSession,
    project_id: uuid.UUID
) -> ProcessingStats:
    """Get processing statistics for a project."""
    # Count runs
    runs_result = await db.execute(
        select(func.count(ProcessingRun.id))
        .where(ProcessingRun.project_id == project_id)
    )
    total_runs = runs_result.scalar() or 0
    
    completed_result = await db.execute(
        select(func.count(ProcessingRun.id))
        .where(ProcessingRun.project_id == project_id)
        .where(ProcessingRun.status == "completed")
    )
    completed_runs = completed_result.scalar() or 0
    
    failed_result = await db.execute(
        select(func.count(ProcessingRun.id))
        .where(ProcessingRun.project_id == project_id)
        .where(ProcessingRun.status == "failed")
    )
    failed_runs = failed_result.scalar() or 0
    
    # Count detections
    detections_result = await db.execute(
        select(func.count(Detection.id))
        .where(Detection.project_id == project_id)
    )
    total_detections = detections_result.scalar() or 0
    
    # Count unique tracks
    tracks_result = await db.execute(
        select(func.count(func.distinct(Detection.track_id)))
        .where(Detection.project_id == project_id)
        .where(Detection.track_id.isnot(None))
    )
    unique_tracks = tracks_result.scalar() or 0
    
    # Sum processed frames
    frames_result = await db.execute(
        select(func.sum(ProcessingRun.processed_frames))
        .where(ProcessingRun.project_id == project_id)
        .where(ProcessingRun.status == "completed")
    )
    total_frames_processed = frames_result.scalar() or 0
    
    return ProcessingStats(
        total_runs=total_runs,
        completed_runs=completed_runs,
        failed_runs=failed_runs,
        total_detections=total_detections,
        unique_tracks=unique_tracks,
        total_frames_processed=total_frames_processed or 0
    )


async def delete_project_detections(
    db: AsyncSession,
    project_id: uuid.UUID
) -> int:
    """Delete all detections for a project."""
    result = await db.execute(
        delete(Detection).where(Detection.project_id == project_id)
    )
    await db.commit()
    return result.rowcount

