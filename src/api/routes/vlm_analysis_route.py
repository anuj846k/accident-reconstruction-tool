"""
VLM Analysis API routes using Oumi.

Handles:
- Analyzing collision frames with VLM
- Fine-tuning VLM with RL (REQUIRED for hackathon)
"""

import uuid
import logging
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.api.deps import get_db, get_current_user
from src.models.user import User
from src.models.project import Project
from src.models.detection import Detection
from src.services import processing as processing_service
from src.services.collision_analysis import analyze_collisions, get_key_frames_for_collision
from src.services.oumi_vlm import OumiVLMAnalyzer
from src.services.oumi_rl_finetuning import OumiRLFineTuner
from src.services.frame_extraction import FrameExtractor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vlm-analysis", tags=["vlm-analysis"])


# ============== Request/Response Schemas ==============

class AnalyzeCollisionRequest(BaseModel):
    """Request to analyze collision frames with VLM."""
    project_id: uuid.UUID
    track_id_1: Optional[int] = None  # Optional: if not provided, uses top collision (highest IoU)
    track_id_2: Optional[int] = None  # Optional: if not provided, uses top collision (highest IoU)
    collision_index: Optional[int] = 0  # Which collision if multiple between same tracks


class FrameAnalysisResponse(BaseModel):
    """VLM analysis for a single frame."""
    frame_number: int
    moment: str  # "approach", "contact", "peak", "separation"
    analysis: str
    prompt: Optional[str] = None


class CollisionAnalysisResponse(BaseModel):
    """Complete VLM analysis for a collision."""
    collision_info: dict
    frame_analyses: Dict[str, FrameAnalysisResponse]
    summary: str


class FineTuneRLRequest(BaseModel):
    """Request to fine-tune VLM with RL."""
    project_id: uuid.UUID
    collision_indices: Optional[List[int]] = None  # Which collisions to use for training
    output_dir: Optional[str] = None
    model_name: Optional[str] = None


class FineTuneRLResponse(BaseModel):
    """Response from RL fine-tuning."""
    success: bool
    model_path: Optional[str] = None
    training_config_path: Optional[str] = None
    message: str


# ============== API Endpoints ==============

@router.post("/analyze-collision", response_model=CollisionAnalysisResponse)
async def analyze_collision_with_vlm(
    request: AnalyzeCollisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Analyze collision frames using Oumi VLM.
    
    This endpoint:
    1. Finds the collision (auto-detects top collision if track_ids not provided)
    2. Extracts key frames (approach, contact, peak, separation)
    3. Analyzes each frame with Oumi VLM
    4. Generates a comprehensive report
    
    If track_id_1 and track_id_2 are not provided, automatically uses the collision
    with the highest IoU (most significant collision).
    """
    # Check authorization
    result = await db.execute(
        select(Project).where(Project.id == request.project_id)
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get all detections
    detections = await processing_service.get_all_detections(db, request.project_id, limit=100000)
    
    if not detections:
        raise HTTPException(
            status_code=400,
            detail="No detections found. Please process the video first."
        )
    
    # Find collisions (use same parameters as analysis route)
    analysis_result = analyze_collisions(
        detections,
        iou_threshold=0.1,
        distance_threshold=50.0,
        persistence_frames=3,
        min_collision_frames=2
    )
    
    if not analysis_result.collisions:
        raise HTTPException(
            status_code=404,
            detail="No collisions found. Please ensure the video has been processed and collisions detected."
        )
    
    # Filter to top collision (same as analysis route) - sort by max_iou
    collisions_to_search = analysis_result.collisions
    if collisions_to_search:
        # Sort by max_iou descending, then by duration (longer = more significant)
        collisions_to_search = sorted(
            collisions_to_search,
            key=lambda c: (-c.max_iou, -c.duration_frames)
        )
    
    # If track_ids provided, try to find that specific collision
    if request.track_id_1 is not None and request.track_id_2 is not None:
        matching_collisions = [
            c for c in collisions_to_search
            if (c.track_id_1 == request.track_id_1 and c.track_id_2 == request.track_id_2) or
               (c.track_id_1 == request.track_id_2 and c.track_id_2 == request.track_id_1)
        ]
        
        if matching_collisions:
            collision = matching_collisions[
                request.collision_index if request.collision_index < len(matching_collisions) else 0
            ]
            logger.info(
                f"Found collision for tracks {request.track_id_1} and {request.track_id_2}: "
                f"IoU={collision.max_iou:.3f}"
            )
        else:
            # Fallback to top collision if specific tracks not found
            logger.warning(
                f"No collision found for tracks {request.track_id_1} and {request.track_id_2}. "
                f"Using top collision instead: Track {collisions_to_search[0].track_id_1} vs "
                f"Track {collisions_to_search[0].track_id_2}, IoU={collisions_to_search[0].max_iou:.3f}"
            )
            collision = collisions_to_search[0]
    else:
        # Auto-detect: use top collision (highest IoU)
        collision = collisions_to_search[0]
        logger.info(
            f"Auto-selected top collision: Track {collision.track_id_1} vs Track {collision.track_id_2}, "
            f"IoU={collision.max_iou:.3f}, Duration={collision.duration_frames} frames"
        )
    
    # Get key frames
    key_frames = get_key_frames_for_collision(
        detections,
        collision
    )
    
    # Get video URL from project
    from src.models.media_asset import MediaAsset, MediaAssetKind
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
            detail="No video found for this project"
        )
    
    # Extract frames
    extractor = FrameExtractor()
    frames_data = await extractor.extract_key_frames_for_collision(
        video_asset.uri,
        key_frames,
        collision
    )
    
    # Analyze with Oumi VLM
    analyzer = OumiVLMAnalyzer()
    frame_analyses = analyzer.analyze_collision_frames(
        frames_data,
        {
            "track_id_1": collision.track_id_1,
            "track_id_2": collision.track_id_2,
            "max_iou": collision.max_iou,
            "severity": collision.severity,
            "duration_frames": collision.duration_frames
        }
    )
    
    # Generate summary
    summary = analyzer.generate_collision_summary(
        frame_analyses,
        {
            "track_id_1": collision.track_id_1,
            "track_id_2": collision.track_id_2,
            "max_iou": collision.max_iou,
            "severity": collision.severity,
            "duration_frames": collision.duration_frames
        }
    )
    
    # Format response
    formatted_analyses = {}
    for moment, analysis_data in frame_analyses.items():
        formatted_analyses[moment] = FrameAnalysisResponse(
            frame_number=analysis_data.get("frame_number", 0),
            moment=moment,
            analysis=analysis_data.get("analysis", ""),
            prompt=analysis_data.get("prompt")
        )
    
    return CollisionAnalysisResponse(
        collision_info={
            "track_id_1": collision.track_id_1,
            "track_id_2": collision.track_id_2,
            "first_contact_frame": collision.first_contact_frame,
            "last_overlap_frame": collision.last_overlap_frame,
            "peak_overlap_frame": collision.peak_overlap_frame,
            "max_iou": collision.max_iou,
            "min_distance": collision.min_distance,
            "duration_frames": collision.duration_frames,
            "severity": collision.severity
        },
        frame_analyses=formatted_analyses,
        summary=summary
    )


@router.post("/fine-tune-with-rl", response_model=FineTuneRLResponse)
async def fine_tune_vlm_with_rl(
    request: FineTuneRLRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Fine-tune VLM using Oumi's Reinforcement Learning (RLHF).
    
    This is the REQUIRED feature for the hackathon award.
    
    The fine-tuning process:
    1. Collects collision frames from the project
    2. Prepares training dataset
    3. Uses Oumi's RL fine-tuning to improve VLM for accident analysis
    """
    # Check authorization
    result = await db.execute(
        select(Project).where(Project.id == request.project_id)
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    try:
        # Get detections and find collisions
        detections = await processing_service.get_all_detections(db, request.project_id, limit=100000)
        
        if not detections:
            raise HTTPException(
                status_code=400,
                detail="No detections found. Please process the video first."
            )
        
        # Find collisions (use same parameters as analysis route)
        analysis_result = analyze_collisions(
            detections,
            iou_threshold=0.1,
            distance_threshold=50.0,
            persistence_frames=3,
            min_collision_frames=2
        )
        
        if not analysis_result.collisions:
            raise HTTPException(
                status_code=400,
                detail="No collisions found. Cannot fine-tune without collision data."
            )
        
        # Filter to top collisions (sort by max_iou)
        collisions_to_search = analysis_result.collisions
        if collisions_to_search:
            # Sort by max_iou descending, then by duration
            collisions_to_search = sorted(
                collisions_to_search,
                key=lambda c: (-c.max_iou, -c.duration_frames)
            )
        
        # Select collisions to use
        if request.collision_indices:
            # Use specified collision indices
            collisions_to_use = [
                collisions_to_search[i]
                for i in request.collision_indices
                if i < len(collisions_to_search)
            ]
        else:
            # Default: use top collision (highest IoU)
            collisions_to_use = [collisions_to_search[0]]
            logger.info(
                f"Using top collision for RL training: Track {collisions_to_use[0].track_id_1} vs "
                f"Track {collisions_to_use[0].track_id_2}, IoU={collisions_to_use[0].max_iou:.3f}"
            )
        
        if not collisions_to_use:
            raise HTTPException(
                status_code=400,
                detail="No valid collisions selected for training"
            )
        
        # Get video URL
        from src.models.media_asset import MediaAsset, MediaAssetKind
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
                detail="No video found for this project"
            )
        
        # Prepare training data (extract frames for each collision)
        extractor = FrameExtractor()
        training_frames = []
        
        for collision in collisions_to_use:
            key_frames = get_key_frames_for_collision(
                detections,
                collision
            )
            
            frames_data = await extractor.extract_key_frames_for_collision(
                video_asset.uri,
                key_frames,
                collision
            )
            
            # Add to training data
            for moment, frame_data in frames_data.items():
                if "image_base64" in frame_data:
                    training_frames.append({
                        "image_base64": frame_data["image_base64"],
                        "frame_number": frame_data.get("frame_number", 0),
                        "moment": moment,
                        "collision_info": {
                            "track_id_1": collision.track_id_1,
                            "track_id_2": collision.track_id_2,
                            "severity": collision.severity
                        }
                    })
        
        if not training_frames:
            raise HTTPException(
                status_code=400,
                detail="Failed to extract frames for training"
            )
        
        # Initialize fine-tuner
        fine_tuner = OumiRLFineTuner()
        
        # Set output directory
        output_dir = None
        if request.output_dir:
            output_dir = Path(request.output_dir)
        
        # Run fine-tuning (this can take a while, consider making it async/background)
        logger.info(f"Starting RL fine-tuning with {len(training_frames)} frames")
        result = fine_tuner.fine_tune_with_oumi_rl(
            training_frames,
            output_dir=output_dir,
            model_name=request.model_name
        )
        
        return FineTuneRLResponse(
            success=True,
            model_path=str(result.get("model_path", "")),
            training_config_path=str(result.get("config_path", "")),
            message=f"Successfully fine-tuned model with {len(training_frames)} frames"
        )
        
    except Exception as e:
        logger.error(f"RL fine-tuning failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Fine-tuning failed: {str(e)}"
        )

