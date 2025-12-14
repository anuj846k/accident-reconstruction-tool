"""
Processing API routes for video analysis.

Handles:
- Starting video processing
- Getting processing status
- Retrieving detection results
- Integration with homography calibration for speed calculation
"""

import uuid
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.api.deps import get_db, get_current_user
from src.models.user import User
from src.models.project import Project, ProjectStatus
from src.models.media_asset import MediaAsset, MediaAssetKind
from src.models.homography import HomographySession, HomographyModel
from src.services import processing as processing_service
from src.services.video_processor import VideoProcessor, ProcessingConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/processing", tags=["processing"])


# ============== Request/Response Schemas ==============

class StartProcessingRequest(BaseModel):
    """Request to start video processing."""
    project_id: uuid.UUID
    config: Optional[dict] = None


class StartProcessingResponse(BaseModel):
    """Response after starting processing."""
    run_id: uuid.UUID
    status: str
    message: str

class ProcessingStatusResponse(BaseModel):
    """Response with processing status."""
    run_id: uuid.UUID
    status: str
    total_frames: Optional[int] = None
    processed_frames: int = 0
    detection_count: int = 0
    unique_tracks: int = 0
    error_message: Optional[str] = None


class DetectionResponse(BaseModel):
    """Single detection response."""
    id: uuid.UUID
    frame_idx: int
    timestamp_ms: int
    track_id: Optional[int]
    class_name: str
    confidence: float
    bbox_x: float
    bbox_y: float
    bbox_w: float
    bbox_h: float
    center_x: float
    center_y: float
    # Calibration-based fields (populated when homography is available)
    speed_mph: Optional[float] = None
    world_x: Optional[float] = None
    world_y: Optional[float] = None


class DetectionsListResponse(BaseModel):
    """List of detections response."""
    project_id: uuid.UUID
    total_count: int
    detections: List[DetectionResponse]


class TrackListResponse(BaseModel):
    """List of unique tracks."""
    project_id: uuid.UUID
    track_ids: List[int]
    total_tracks: int


# ============== Background Task ==============

async def process_video_task(
    run_id: uuid.UUID,
    project_id: uuid.UUID,
    video_url: str,
    config: Optional[dict],
    homography_matrix: Optional[List[List[float]]],
    db_url: str
):
    """
    Background task to process video.
    
    This runs in background after the API returns.
    If homography_matrix is provided, will calculate real-world speeds.
    
    Args:
        run_id: Processing run ID
        project_id: Project ID
        video_url: URL of the video to process
        config: Optional processing configuration
        homography_matrix: Optional 3x3 homography matrix for speed calculation
        db_url: Database connection URL
    """
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    # Create new database session for background task
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        try:
            # Update status to processing
            await processing_service.update_processing_run_status(
                db, run_id, "processing"
            )
            
            # Initialize processor config
            proc_config = ProcessingConfig()
            if config:
                if "conf_threshold" in config:
                    proc_config.conf_threshold = config["conf_threshold"]
                if "iou_threshold" in config:
                    proc_config.iou_threshold = config["iou_threshold"]
            
            # Initialize processor with homography matrix for speed calculation
            processor = VideoProcessor(proc_config, homography_matrix=homography_matrix)
            
            if homography_matrix:
                logger.info(f"Processing with homography calibration enabled for run {run_id}")
            else:
                logger.info(f"Processing without calibration (no speed calculation) for run {run_id}")
            
            # Process video
            logger.info(f"Starting video processing for run {run_id}")
            detections, video_info = processor.process_video_from_url(video_url)
            
            # Save detections to database (including speed/world coords if available)
            saved_count = await processing_service.save_detections(db, project_id, detections)
            
            # Calculate unique tracks
            unique_tracks = len(set(d.track_id for d in detections if d.track_id is not None))
            
            # Count detections with speed data
            detections_with_speed = sum(1 for d in detections if d.speed_mph is not None)
            
            # Update processing run with results
            await processing_service.update_processing_run_status(
                db,
                run_id,
                "completed",
                total_frames=video_info["total_frames"],
                processed_frames=video_info["total_frames"],
                detection_count=saved_count,
                unique_tracks=unique_tracks
            )
            
            # Update project status
            result = await db.execute(select(Project).where(Project.id == project_id))
            project = result.scalar_one_or_none()
            if project:
                project.status = ProjectStatus.COMPLETED
                await db.commit()
            
            logger.info(
                f"Processing complete for run {run_id}: "
                f"{saved_count} detections, {unique_tracks} tracks, "
                f"{detections_with_speed} with speed data"
            )
            
        except Exception as e:
            logger.error(f"Processing failed for run {run_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await processing_service.update_processing_run_status(
                db, run_id, "failed", error_message=str(e)
            )
            
            # Update project status
            result = await db.execute(select(Project).where(Project.id == project_id))
            project = result.scalar_one_or_none()
            if project:
                project.status = ProjectStatus.FAILED
                await db.commit()


# ============== API Endpoints ==============

@router.post("/start", response_model=StartProcessingResponse)
async def start_processing(
    request: StartProcessingRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Start video processing for a project.
    
    This endpoint:
    1. Validates the project and video
    2. Checks for homography calibration (optional but enables speed calculation)
    3. Creates a processing run record
    4. Starts background processing
    5. Returns immediately with run_id
    
    If homography calibration is available, processing will calculate:
    - Real-world speeds (mph)
    - GPS coordinates for each detection
    """
    from src.core.config import settings
    
    # Get project
    result = await db.execute(
        select(Project).where(Project.id == request.project_id)
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get video asset
    result = await db.execute(
        select(MediaAsset)
        .where(MediaAsset.project_id == request.project_id)
        .where(MediaAsset.kind == MediaAssetKind.VIDEO)
        .order_by(MediaAsset.created_at.desc())
        .limit(1)
    )
    video_asset = result.scalar_one_or_none()
    
    if not video_asset:
        raise HTTPException(
            status_code=400,
            detail="No video found for this project. Please upload a video first."
        )
    
    # Try to get homography matrix if calibration is available
    homography_matrix: Optional[List[List[float]]] = None
    calibration_status = "not_available"
    
    try:
        # Check for solved homography session
        result = await db.execute(
            select(HomographySession)
            .where(HomographySession.project_id == request.project_id)
            .where(HomographySession.status == "solved")
        )
        homography_session = result.scalar_one_or_none()
        
        if homography_session:
            # Get the homography model with the matrix
            result = await db.execute(
                select(HomographyModel)
                .where(HomographyModel.session_id == homography_session.id)
            )
            homography_model = result.scalar_one_or_none()
            
            if homography_model and homography_model.matrix_data:
                homography_matrix = homography_model.matrix_data
                calibration_status = "enabled"
                logger.info(f"Homography calibration found for project {request.project_id}")
    except Exception as e:
        logger.warning(f"Failed to fetch homography for project {request.project_id}: {e}")
        calibration_status = "error"
    
    # Create processing run
    run = await processing_service.create_processing_run(
        db,
        processing_service.ProcessingRunCreate(
            project_id=request.project_id,
            video_uri=video_asset.uri,
            config=request.config
        )
    )
    
    # Update project status
    project.status = ProjectStatus.PROCESSING
    await db.commit()
    
    # Start background processing with homography matrix
    background_tasks.add_task(
        process_video_task,
        run.id,
        request.project_id,
        video_asset.uri,
        request.config,
        homography_matrix,  # Pass homography matrix
        settings.database_url
    )
    
    # Prepare response message
    if homography_matrix:
        message = "Video processing started with calibration enabled (speed calculation active). Check status with GET /processing/status/{run_id}"
    else:
        message = "Video processing started without calibration (no speed calculation). Add calibration points to enable speed calculation. Check status with GET /processing/status/{run_id}"
    
    return StartProcessingResponse(
        run_id=run.id,
        status="started",
        message=message
    )


@router.get("/status/{run_id}", response_model=ProcessingStatusResponse)
async def get_processing_status(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get the status of a processing run."""
    from sqlalchemy import select
    
    run = await processing_service.get_processing_run(db, run_id)
    
    if not run:
        raise HTTPException(status_code=404, detail="Processing run not found")
    
    # Check authorization
    result = await db.execute(
        select(Project).where(Project.id == run.project_id)
    )
    project = result.scalar_one_or_none()
    
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    return ProcessingStatusResponse(
        run_id=run.id,
        status=run.status,
        total_frames=run.total_frames,
        processed_frames=run.processed_frames,
        detection_count=run.detection_count,
        unique_tracks=run.unique_tracks,
        error_message=run.error_message
    )


@router.get("/project/{project_id}/runs", response_model=List[processing_service.ProcessingRunPublic])
async def list_processing_runs(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all processing runs for a project."""
    from sqlalchemy import select
    
    # Check authorization
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    runs = await processing_service.list_processing_runs(db, project_id)
    return runs


@router.get("/project/{project_id}/detections", response_model=DetectionsListResponse)
async def get_project_detections(
    project_id: uuid.UUID,
    frame_idx: Optional[int] = None,
    track_id: Optional[int] = None,
    limit: int = 1000,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get detections for a project.
    
    Optional filters:
    - frame_idx: Get detections for a specific frame
    - track_id: Get detections for a specific track
    - limit: Maximum number of detections to return
    """
    from sqlalchemy import select
    
    # Check authorization
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get detections based on filters
    if frame_idx is not None:
        detections = await processing_service.get_detections_by_frame(db, project_id, frame_idx)
    elif track_id is not None:
        detections = await processing_service.get_detections_by_track(db, project_id, track_id)
    else:
        detections = await processing_service.get_all_detections(db, project_id, limit)
    
    return DetectionsListResponse(
        project_id=project_id,
        total_count=len(detections),
        detections=[
            DetectionResponse(
                id=d.id,
                frame_idx=d.frame_idx,
                timestamp_ms=d.timestamp_ms,
                track_id=d.track_id,
                class_name=d.class_name,
                confidence=d.confidence,
                bbox_x=d.bbox_x,
                bbox_y=d.bbox_y,
                bbox_w=d.bbox_w,
                bbox_h=d.bbox_h,
                center_x=d.center_x,
                center_y=d.center_y,
                speed_mph=d.speed_mph,
                world_x=d.world_x,
                world_y=d.world_y,
            )
            for d in detections
        ]
    )


@router.get("/project/{project_id}/tracks", response_model=TrackListResponse)
async def get_project_tracks(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get list of unique track IDs for a project."""
    from sqlalchemy import select
    
    # Check authorization
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    track_ids = await processing_service.get_unique_tracks(db, project_id)
    
    return TrackListResponse(
        project_id=project_id,
        track_ids=track_ids,
        total_tracks=len(track_ids)
    )


@router.get("/project/{project_id}/stats", response_model=processing_service.ProcessingStats)
async def get_processing_stats(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get processing statistics for a project."""
    from sqlalchemy import select
    
    # Check authorization
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    stats = await processing_service.get_processing_stats(db, project_id)
    return stats


@router.delete("/project/{project_id}/detections")
async def delete_project_detections(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete all detections for a project (for re-processing)."""
    from sqlalchemy import select
    
    # Check authorization
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    deleted_count = await processing_service.delete_project_detections(db, project_id)
    
    return {
        "message": f"Deleted {deleted_count} detections",
        "deleted_count": deleted_count
    }

