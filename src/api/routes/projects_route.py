import uuid
import logging

from fastapi import APIRouter, HTTPException, UploadFile, File

from src.api.deps import SessionDep, CurrentUser
from src.services.project import (
    ProjectCreate,
    ProjectPublic,
    ProjectsPublic,
    ProjectUpdate,
    create_project,
    get_project,
    list_projects,
    update_project,
    delete_project,
)
from src.services.user import Message
from src.services.media import MediaAssetPublic, create_media_asset
from src.services.storage import upload_video_to_cloudinary
from src.models.media_asset import MediaAssetKind

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("/", response_model=ProjectPublic)
async def create_project_route(
    session: SessionDep,
    project_in: ProjectCreate,
    current_user: CurrentUser,
) -> ProjectPublic:
    """Create a new accident analysis project."""
    try:
        project = await create_project(
            session=session,
            project_create=project_in,
            user_id=current_user.id
        )
        return ProjectPublic.model_validate(project)
    except Exception as e:
        logger.error(f"Error creating project: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/", response_model=ProjectsPublic)
async def read_projects(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
) -> ProjectsPublic:
    """List all projects for current user."""
    try:
        projects, count = await list_projects(
            session=session,
            user_id=current_user.id,
            skip=skip,
            limit=limit
        )
        return ProjectsPublic(
            data=[ProjectPublic.model_validate(p) for p in projects],
            count=count
        )
    except Exception as e:
        logger.error(f"Error listing projects: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{project_id}", response_model=ProjectPublic)
async def read_project(
    session: SessionDep,
    project_id: uuid.UUID,
    current_user: CurrentUser,
) -> ProjectPublic:
    """Get a specific project by ID."""
    project = await get_project(
        session=session,
        project_id=project_id,
        user_id=current_user.id
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectPublic.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectPublic)
async def update_project_route(
    session: SessionDep,
    project_id: uuid.UUID,
    project_in: ProjectUpdate,
    current_user: CurrentUser,
) -> ProjectPublic:
    """Update a project."""
    project = await update_project(
        session=session,
        project_id=project_id,
        user_id=current_user.id,
        project_update=project_in
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectPublic.model_validate(project)


@router.delete("/{project_id}", response_model=Message)
async def delete_project_route(
    session: SessionDep,
    project_id: uuid.UUID,
    current_user: CurrentUser,
) -> Message:
    """Delete a project."""
    success = await delete_project(
        session=session,
        project_id=project_id,
        user_id=current_user.id
    )
    if not success:
        raise HTTPException(status_code=404, detail="Project not found")
    return Message(message="Project deleted successfully")





@router.post("/{project_id}/upload-video", response_model=MediaAssetPublic)
async def upload_video(
    session: SessionDep,
    project_id: uuid.UUID,
    current_user: CurrentUser,
    file: UploadFile = File(...),
) -> MediaAssetPublic:
    """
    Upload a video file for a project.
    
    - Uploads to Cloudinary
    - Creates MediaAsset record in database
    - Returns the media asset with URL
    """
    # Verify project exists and belongs to user
    project = await get_project(session, project_id, current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Validate file is a video
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="File must be a video")
    
    try:
        # Upload to Cloudinary
        upload_result = await upload_video_to_cloudinary(
            file=file,
            project_id=project_id,
        )
        
        # Create database record
        media_asset = await create_media_asset(
            session=session,
            project_id=project_id,
            uri=upload_result["url"],
            file_size=upload_result.get("bytes", 0),
            kind=MediaAssetKind.VIDEO,
            filename=file.filename,
            content_type=file.content_type,
            meta={
                "cloudinary_public_id": upload_result.get("public_id"),
                "duration": upload_result.get("duration"),
                "width": upload_result.get("width"),
                "height": upload_result.get("height"),
                "format": upload_result.get("format"),
            }
        )
        
        # Update project video_path
        project.video_path = upload_result["url"]
        await session.commit()
        
        return MediaAssetPublic.model_validate(media_asset)
        
    except Exception as e:
        logger.error(f"Error uploading video: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload video: {str(e)}")