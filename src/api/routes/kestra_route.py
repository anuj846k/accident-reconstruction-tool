"""
Kestra Integration API routes.

These endpoints are designed to be called by Kestra workflows to:
1. Trigger processing
2. Get collision data
3. Save AI summaries
4. Get workflow status

Replaces Celery for background task orchestration.
"""

import uuid
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.api.deps import get_db, get_current_user
from src.models.user import User
from src.models.project import Project, ProjectStatus
from src.models.ai_summary import AISummary
from src.services import processing as processing_service
from src.services.collision_analysis import analyze_collisions, get_key_frames_for_collision

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kestra", tags=["kestra"])


# ============== Request/Response Schemas ==============

class TriggerWorkflowRequest(BaseModel):
    """Request to trigger Kestra workflow for a project."""
    project_id: uuid.UUID


class TriggerWorkflowResponse(BaseModel):
    """Response after triggering workflow."""
    project_id: uuid.UUID
    status: str
    message: str
    processing_run_id: Optional[uuid.UUID] = None


class SaveSummaryRequest(BaseModel):
    """Request to save AI-generated summary (called by Kestra)."""
    project_id: uuid.UUID
    summary_text: str = Field(..., description="AI-generated narrative")
    severity_assessment: Optional[str] = None
    recommendations: Optional[str] = None
    collision_data: Optional[Dict[str, Any]] = None
    ai_model: Optional[str] = "gpt-4o-mini"
    kestra_execution_id: Optional[str] = None


class SaveSummaryResponse(BaseModel):
    """Response after saving summary."""
    summary_id: uuid.UUID
    project_id: uuid.UUID
    message: str


class CollisionDataResponse(BaseModel):
    """Collision data formatted for Kestra/AI consumption."""
    project_id: uuid.UUID
    has_collisions: bool
    collision_count: int
    top_collision: Optional[Dict[str, Any]] = None
    all_collisions: List[Dict[str, Any]] = []
    analysis_summary: Dict[str, Any] = {}


class WorkflowStatusResponse(BaseModel):
    """Complete status for Kestra workflow."""
    project_id: uuid.UUID
    project_status: str
    has_video: bool
    processing_status: Optional[str] = None
    processing_run_id: Optional[uuid.UUID] = None
    detection_count: int = 0
    collision_count: int = 0
    has_ai_summary: bool = False
    latest_summary_id: Optional[uuid.UUID] = None


class SummaryResponse(BaseModel):
    """AI Summary response."""
    id: uuid.UUID
    project_id: uuid.UUID
    summary_text: str
    severity_assessment: Optional[str]
    recommendations: Optional[str]
    ai_model: Optional[str]
    created_at: datetime


# ============== API Endpoints ==============

@router.post("/trigger-analysis", response_model=TriggerWorkflowResponse)
async def trigger_kestra_analysis(
    request: TriggerWorkflowRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Trigger analysis workflow for a project.
    
    This endpoint is called to start the Kestra workflow.
    It validates the project and returns status for Kestra to proceed.
    """
    # Get project
    result = await db.execute(
        select(Project).where(Project.id == request.project_id)
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Check if video exists
    from src.models.media_asset import MediaAsset, MediaAssetKind
    result = await db.execute(
        select(MediaAsset)
        .where(MediaAsset.project_id == request.project_id)
        .where(MediaAsset.kind == MediaAssetKind.VIDEO)
        .limit(1)
    )
    video_asset = result.scalar_one_or_none()
    
    if not video_asset:
        raise HTTPException(
            status_code=400,
            detail="No video uploaded. Please upload a video first."
        )
    
    # Check if already processed
    if project.status == ProjectStatus.COMPLETED:
        return TriggerWorkflowResponse(
            project_id=request.project_id,
            status="already_processed",
            message="Project already processed. Kestra can proceed to AI analysis."
        )
    
    if project.status == ProjectStatus.PROCESSING:
        # Get latest run
        runs = await processing_service.list_processing_runs(db, request.project_id)
        latest_run_id = runs[0].id if runs else None
        
        return TriggerWorkflowResponse(
            project_id=request.project_id,
            status="processing",
            message="Video processing in progress.",
            processing_run_id=latest_run_id
        )
    
    return TriggerWorkflowResponse(
        project_id=request.project_id,
        status="ready",
        message="Project ready for processing. Call /processing/start to begin."
    )


@router.get("/project/{project_id}/collision-data", response_model=CollisionDataResponse)
async def get_collision_data_for_kestra(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get collision data formatted for Kestra AI analysis.
    
    Returns collision data in a format optimized for AI summarization.
    Kestra calls this endpoint, then passes the data to OpenAI/Claude.
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
    
    # Get detections
    detections = await processing_service.get_all_detections(db, project_id, limit=100000)
    
    if not detections:
        return CollisionDataResponse(
            project_id=project_id,
            has_collisions=False,
            collision_count=0,
            analysis_summary={"message": "No detections found. Process video first."}
        )
    
    # Analyze collisions
    analysis_result = analyze_collisions(
        detections,
        iou_threshold=0.1,
        distance_threshold=50.0,
        persistence_frames=3,
        min_collision_frames=2
    )
    
    if not analysis_result.collisions:
        return CollisionDataResponse(
            project_id=project_id,
            has_collisions=False,
            collision_count=0,
            analysis_summary={
                "total_detections": len(detections),
                "unique_tracks": len(set(d.track_id for d in detections if d.track_id)),
                "message": "No collisions detected in video."
            }
        )
    
    # Sort by significance (IoU)
    sorted_collisions = sorted(
        analysis_result.collisions,
        key=lambda c: (-c.max_iou, -c.duration_frames)
    )
    
    # Format for AI consumption
    all_collisions = []
    for collision in sorted_collisions:
        key_frames = get_key_frames_for_collision(detections, collision)
        all_collisions.append({
            "track_id_1": collision.track_id_1,
            "track_id_2": collision.track_id_2,
            "severity": collision.severity,
            "max_iou": round(collision.max_iou, 4),
            "min_distance_pixels": round(collision.min_distance, 2),
            "duration_frames": collision.duration_frames,
            "first_contact_frame": collision.first_contact_frame,
            "peak_overlap_frame": collision.peak_overlap_frame,
            "last_overlap_frame": collision.last_overlap_frame,
            "key_frames": key_frames
        })
    
    # Top collision (highest IoU)
    top_collision = all_collisions[0] if all_collisions else None
    
    unique_tracks = len(set(d.track_id for d in detections if d.track_id))
    total_frames = len(set(d.frame_idx for d in detections))
    
    return CollisionDataResponse(
        project_id=project_id,
        has_collisions=True,
        collision_count=len(all_collisions),
        top_collision=top_collision,
        all_collisions=all_collisions,
        analysis_summary={
            "total_detections": len(detections),
            "total_frames": total_frames,
            "unique_tracks": unique_tracks,
            "collision_count": len(all_collisions),
            "most_severe": top_collision["severity"] if top_collision else None
        }
    )


@router.post("/project/{project_id}/save-summary", response_model=SaveSummaryResponse)
async def save_ai_summary(
    project_id: uuid.UUID,
    request: SaveSummaryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Save AI-generated summary (called by Kestra workflow).
    
    After Kestra's AI plugin (OpenAI/Claude) generates a summary,
    it calls this endpoint to persist the result.
    """
    # Verify project_id matches
    if project_id != request.project_id:
        raise HTTPException(status_code=400, detail="Project ID mismatch")
    
    # Check authorization
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Create AI summary record
    ai_summary = AISummary(
        project_id=project_id,
        summary_text=request.summary_text,
        severity_assessment=request.severity_assessment,
        recommendations=request.recommendations,
        collision_data=request.collision_data,
        ai_model=request.ai_model,
        kestra_execution_id=request.kestra_execution_id
    )
    
    db.add(ai_summary)
    await db.commit()
    await db.refresh(ai_summary)
    
    logger.info(f"Saved AI summary {ai_summary.id} for project {project_id}")
    
    return SaveSummaryResponse(
        summary_id=ai_summary.id,
        project_id=project_id,
        message="AI summary saved successfully"
    )


@router.get("/project/{project_id}/status", response_model=WorkflowStatusResponse)
async def get_workflow_status(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get complete workflow status for Kestra.
    
    Returns all relevant status information for Kestra to make decisions.
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
    
    # Check for video
    from src.models.media_asset import MediaAsset, MediaAssetKind
    result = await db.execute(
        select(MediaAsset)
        .where(MediaAsset.project_id == project_id)
        .where(MediaAsset.kind == MediaAssetKind.VIDEO)
        .limit(1)
    )
    has_video = result.scalar_one_or_none() is not None
    
    # Get processing runs
    runs = await processing_service.list_processing_runs(db, project_id)
    latest_run = runs[0] if runs else None
    
    # Get detection count
    detections = await processing_service.get_all_detections(db, project_id, limit=1)
    stats = await processing_service.get_processing_stats(db, project_id)
    
    # Get collision count
    collision_count = 0
    if stats.total_detections > 0:
        all_detections = await processing_service.get_all_detections(db, project_id, limit=100000)
        analysis_result = analyze_collisions(all_detections)
        collision_count = analysis_result.total_collisions
    
    # Check for AI summaries
    result = await db.execute(
        select(AISummary)
        .where(AISummary.project_id == project_id)
        .order_by(AISummary.created_at.desc())
        .limit(1)
    )
    latest_summary = result.scalar_one_or_none()
    
    return WorkflowStatusResponse(
        project_id=project_id,
        project_status=project.status.value,
        has_video=has_video,
        processing_status=latest_run.status if latest_run else None,
        processing_run_id=latest_run.id if latest_run else None,
        detection_count=stats.total_detections,
        collision_count=collision_count,
        has_ai_summary=latest_summary is not None,
        latest_summary_id=latest_summary.id if latest_summary else None
    )


@router.get("/project/{project_id}/summaries", response_model=List[SummaryResponse])
async def get_project_summaries(
    project_id: uuid.UUID,
    limit: int = Query(10, description="Maximum summaries to return"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get AI summaries for a project.
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
    
    # Get summaries
    result = await db.execute(
        select(AISummary)
        .where(AISummary.project_id == project_id)
        .order_by(AISummary.created_at.desc())
        .limit(limit)
    )
    summaries = result.scalars().all()
    
    return [
        SummaryResponse(
            id=s.id,
            project_id=s.project_id,
            summary_text=s.summary_text,
            severity_assessment=s.severity_assessment,
            recommendations=s.recommendations,
            ai_model=s.ai_model,
            created_at=s.created_at
        )
        for s in summaries
    ]


@router.get("/project/{project_id}/summary/{summary_id}", response_model=SummaryResponse)
async def get_summary_detail(
    project_id: uuid.UUID,
    summary_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get a specific AI summary.
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
    
    # Get summary
    result = await db.execute(
        select(AISummary)
        .where(AISummary.id == summary_id)
        .where(AISummary.project_id == project_id)
    )
    summary = result.scalar_one_or_none()
    
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")
    
    return SummaryResponse(
        id=summary.id,
        project_id=summary.project_id,
        summary_text=summary.summary_text,
        severity_assessment=summary.severity_assessment,
        recommendations=summary.recommendations,
        ai_model=summary.ai_model,
        created_at=summary.created_at
    )


# ============== BATCH PROCESSING ENDPOINTS ==============

class PendingProjectsResponse(BaseModel):
    """Response with list of pending projects for batch processing."""
    count: int
    project_ids: List[str]
    projects: List[Dict[str, Any]] = []


@router.get("/pending-projects", response_model=PendingProjectsResponse)
async def get_pending_projects(
    limit: int = Query(100, description="Max projects to return"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all projects pending analysis (for batch processing).
    
    Used by Kestra's batch-processing workflow to:
    1. Find all projects that have videos but haven't been analyzed
    2. Loop through each and run the analysis pipeline
    
    A project is "pending" if:
    - Has a video uploaded
    - Status is not COMPLETED
    - No AI summary exists yet
    """
    from src.models.media_asset import MediaAsset, MediaAssetKind
    from sqlalchemy import and_, exists, not_
    
    # Subquery: projects that have video
    has_video = (
        select(MediaAsset.project_id)
        .where(MediaAsset.kind == MediaAssetKind.VIDEO)
        .distinct()
    ).subquery()
    
    # Subquery: projects that already have AI summary
    has_summary = (
        select(AISummary.project_id)
        .distinct()
    ).subquery()
    
    # Get pending projects (have video, no summary, not completed)
    result = await db.execute(
        select(Project)
        .where(Project.user_id == current_user.id)
        .where(Project.id.in_(select(has_video)))
        .where(~Project.id.in_(select(has_summary)))
        .where(Project.status != ProjectStatus.COMPLETED)
        .limit(limit)
    )
    projects = result.scalars().all()
    
    project_ids = [str(p.id) for p in projects]
    project_details = [
        {
            "id": str(p.id),
            "name": p.name,
            "status": p.status.value,
            "created_at": p.created_at.isoformat() if p.created_at else None
        }
        for p in projects
    ]
    
    logger.info(f"Found {len(project_ids)} pending projects for batch processing")
    
    return PendingProjectsResponse(
        count=len(project_ids),
        project_ids=project_ids,
        projects=project_details
    )


@router.get("/batch-stats")
async def get_batch_processing_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get statistics for batch processing dashboard.
    
    Returns counts of projects in different states.
    """
    from src.models.media_asset import MediaAsset, MediaAssetKind
    
    # Total projects
    result = await db.execute(
        select(Project).where(Project.user_id == current_user.id)
    )
    all_projects = result.scalars().all()
    total_projects = len(all_projects)
    
    # Projects with video
    result = await db.execute(
        select(Project)
        .join(MediaAsset, MediaAsset.project_id == Project.id)
        .where(Project.user_id == current_user.id)
        .where(MediaAsset.kind == MediaAssetKind.VIDEO)
        .distinct()
    )
    projects_with_video = len(result.scalars().all())
    
    # Projects with AI summary
    result = await db.execute(
        select(Project)
        .join(AISummary, AISummary.project_id == Project.id)
        .where(Project.user_id == current_user.id)
        .distinct()
    )
    projects_with_summary = len(result.scalars().all())
    
    # Projects by status
    status_counts = {}
    for project in all_projects:
        status = project.status.value
        status_counts[status] = status_counts.get(status, 0) + 1
    
    return {
        "total_projects": total_projects,
        "projects_with_video": projects_with_video,
        "projects_with_ai_summary": projects_with_summary,
        "pending_analysis": projects_with_video - projects_with_summary,
        "status_breakdown": status_counts
    }

