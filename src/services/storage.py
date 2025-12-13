import uuid
import cloudinary
import cloudinary.uploader
from typing import Optional
from fastapi import UploadFile

from src.core.config import settings


def init_cloudinary():
    """Initialize Cloudinary with credentials."""
    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        secure=True
    )


async def upload_video_to_cloudinary(
    file: UploadFile,
    project_id: uuid.UUID,
    folder: str = "accident-videos"
) -> dict:
    """
    Upload video to Cloudinary.
    
    Returns dict with:
    - url: Public URL of the video
    - public_id: Cloudinary resource ID
    - duration: Video duration in seconds
    - format: File format (mp4, etc.)
    - bytes: File size
    """
    init_cloudinary()
    
    # Read file content
    content = await file.read()
    
    # Generate unique public_id
    public_id = f"{folder}/{project_id}/{uuid.uuid4()}"
    
    # Upload to Cloudinary
    result = cloudinary.uploader.upload(
        content,
        resource_type="video",
        public_id=public_id,
        folder=None,  # Already included in public_id
    )
    
    return {
        "url": result.get("secure_url"),
        "public_id": result.get("public_id"),
        "duration": result.get("duration"),
        "format": result.get("format"),
        "bytes": result.get("bytes"),
        "width": result.get("width"),
        "height": result.get("height"),
    }


def get_video_url(public_id: str) -> str:
    """Get the URL for a Cloudinary video."""
    init_cloudinary()
    return cloudinary.CloudinaryVideo(public_id).build_url()


def delete_video(public_id: str) -> bool:
    """Delete a video from Cloudinary."""
    init_cloudinary()
    result = cloudinary.uploader.destroy(public_id, resource_type="video")
    return result.get("result") == "ok"