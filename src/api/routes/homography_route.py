"""Homography/Calibration API routes."""

import uuid
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.api.deps import get_db, get_current_user
from src.models.user import User
from src.models.project import Project
from src.models.homography import HomographySession, HomographyPair, HomographyModel
from src.services.homography_solver import solve_homography_from_pairs

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/homography", tags=["homography"])


# ============== Schemas ==============

class PairCreate(BaseModel):
    image_x_norm: float = Field(..., ge=0.0, le=1.0)
    image_y_norm: float = Field(..., ge=0.0, le=1.0)
    map_lat: float
    map_lng: float
    order_idx: int = 0


class PairResponse(BaseModel):
    id: uuid.UUID
    image_x_norm: float
    image_y_norm: float
    map_lat: float
    map_lng: float
    order_idx: int

    class Config:
        from_attributes = True


class SessionResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    status: str
    created_at: datetime
    solved_at: Optional[datetime]
    pairs: List[PairResponse] = []
    matrix: Optional[List[List[float]]] = None
    reprojection_error: Optional[float] = None

    class Config:
        from_attributes = True


class SolveResponse(BaseModel):
    success: bool
    matrix: Optional[List[List[float]]] = None
    reprojection_error: Optional[float] = None
    error_message: Optional[str] = None


# ============== Endpoints ==============

@router.post("/project/{project_id}/session", response_model=SessionResponse)
async def get_or_create_session(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get or create homography session for a project."""
    # Verify project ownership
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Check for existing session
    result = await db.execute(
        select(HomographySession).where(HomographySession.project_id == project_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        session = HomographySession(project_id=project_id, status="draft")
        db.add(session)
        await db.commit()
        await db.refresh(session)
    
    # Load pairs
    result = await db.execute(
        select(HomographyPair)
        .where(HomographyPair.session_id == session.id)
        .order_by(HomographyPair.order_idx)
    )
    pairs = result.scalars().all()
    
    # Load model if solved
    matrix = None
    reprojection_error = None
    if session.status == "solved":
        result = await db.execute(
            select(HomographyModel).where(HomographyModel.session_id == session.id)
        )
        model = result.scalar_one_or_none()
        if model:
            matrix = model.matrix_data
            reprojection_error = model.reprojection_error
    
    return SessionResponse(
        id=session.id,
        project_id=session.project_id,
        status=session.status,
        created_at=session.created_at,
        solved_at=session.solved_at,
        pairs=[PairResponse.model_validate(p) for p in pairs],
        matrix=matrix,
        reprojection_error=reprojection_error
    )


@router.put("/session/{session_id}/pairs", response_model=List[PairResponse])
async def update_pairs(
    session_id: uuid.UUID,
    pairs_data: List[PairCreate],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Replace all pairs in session (bulk update)."""
    # Get session
    result = await db.execute(
        select(HomographySession).where(HomographySession.id == session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Verify ownership through project
    result = await db.execute(select(Project).where(Project.id == session.project_id))
    project = result.scalar_one_or_none()
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Delete existing pairs
    result = await db.execute(
        select(HomographyPair).where(HomographyPair.session_id == session_id)
    )
    existing_pairs = result.scalars().all()
    for pair in existing_pairs:
        await db.delete(pair)
    
    # Add new pairs
    new_pairs = []
    for i, pair_data in enumerate(pairs_data):
        pair = HomographyPair(
            session_id=session_id,
            image_x_norm=pair_data.image_x_norm,
            image_y_norm=pair_data.image_y_norm,
            map_lat=pair_data.map_lat,
            map_lng=pair_data.map_lng,
            order_idx=pair_data.order_idx if pair_data.order_idx else i
        )
        db.add(pair)
        new_pairs.append(pair)
    
    # Reset session status
    session.status = "draft"
    session.solved_at = None
    
    await db.commit()
    
    for pair in new_pairs:
        await db.refresh(pair)
    
    return [PairResponse.model_validate(p) for p in new_pairs]


@router.post("/session/{session_id}/solve", response_model=SolveResponse)
async def solve_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Solve homography matrix from calibration points."""
    # Get session with pairs
    result = await db.execute(
        select(HomographySession).where(HomographySession.id == session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Verify ownership
    result = await db.execute(select(Project).where(Project.id == session.project_id))
    project = result.scalar_one_or_none()
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get pairs
    result = await db.execute(
        select(HomographyPair)
        .where(HomographyPair.session_id == session_id)
        .order_by(HomographyPair.order_idx)
    )
    pairs = result.scalars().all()
    
    if len(pairs) < 4:
        return SolveResponse(
            success=False,
            error_message="At least 4 calibration points required"
        )
    
    try:
        # Solve homography
        result = solve_homography_from_pairs(pairs)
        
        # Delete existing model if any
        existing = await db.execute(
            select(HomographyModel).where(HomographyModel.session_id == session_id)
        )
        existing_model = existing.scalar_one_or_none()
        if existing_model:
            await db.delete(existing_model)
        
        # Create new model
        model = HomographyModel(
            session_id=session_id,
            matrix_data=result.matrix,
            reprojection_error=result.reprojection_error,
            meta={
                "inlier_count": result.inlier_count,
                "total_pairs": len(pairs)
            }
        )
        db.add(model)
        
        # Update session status
        session.status = "solved"
        session.solved_at = datetime.utcnow()
        
        await db.commit()
        
        return SolveResponse(
            success=True,
            matrix=result.matrix,
            reprojection_error=result.reprojection_error
        )
        
    except ValueError as e:
        return SolveResponse(success=False, error_message=str(e))


@router.get("/session/{session_id}/export")
async def export_homography(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export homography data for video processing."""
    result = await db.execute(
        select(HomographySession).where(HomographySession.id == session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Verify ownership
    result = await db.execute(select(Project).where(Project.id == session.project_id))
    project = result.scalar_one_or_none()
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get pairs
    result = await db.execute(
        select(HomographyPair)
        .where(HomographyPair.session_id == session_id)
        .order_by(HomographyPair.order_idx)
    )
    pairs = result.scalars().all()
    
    # Get model
    result = await db.execute(
        select(HomographyModel).where(HomographyModel.session_id == session_id)
    )
    model = result.scalar_one_or_none()
    
    return {
        "pairs": [
            {
                "id": i,
                "a": {"xNorm": p.image_x_norm, "yNorm": p.image_y_norm},
                "b": {"lat": p.map_lat, "lng": p.map_lng}
            }
            for i, p in enumerate(pairs)
        ],
        "matrix": model.matrix_data if model else None,
        "status": session.status
    }