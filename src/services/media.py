import uuid
from typing import Optional
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.media_asset import MediaAsset, MediaAssetKind, ProcessingStatus


# --- Pydantic Schemas ---

class MediaAssetPublic(BaseModel):
    """Schema for returning media asset data."""
    id: uuid.UUID
    project_id: uuid.UUID
    kind: MediaAssetKind
    uri: str
    file_size: int
    filename: Optional[str] = None
    content_type: Optional[str] = None
    processing_status: ProcessingStatus
    meta: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True


# --- CRUD Functions ---

async def create_media_asset(
    session: AsyncSession,
    project_id: uuid.UUID,
    uri: str,
    file_size: int,
    kind: MediaAssetKind = MediaAssetKind.VIDEO,
    filename: Optional[str] = None,
    content_type: Optional[str] = None,
    meta: Optional[dict] = None,
) -> MediaAsset:
    """Create a new media asset record."""
    asset = MediaAsset(
        project_id=project_id,
        kind=kind,
        uri=uri,
        file_size=file_size,
        filename=filename,
        content_type=content_type,
        meta=meta,
        processing_status=ProcessingStatus.PENDING,
    )
    session.add(asset)
    await session.commit()
    await session.refresh(asset)
    return asset


async def get_media_asset(
    session: AsyncSession,
    asset_id: uuid.UUID
) -> Optional[MediaAsset]:
    """Get a media asset by ID."""
    result = await session.execute(
        select(MediaAsset).where(MediaAsset.id == asset_id)
    )
    return result.scalar_one_or_none()


async def get_project_videos(
    session: AsyncSession,
    project_id: uuid.UUID
) -> list[MediaAsset]:
    """Get all videos for a project."""
    result = await session.execute(
        select(MediaAsset).where(
            MediaAsset.project_id == project_id,
            MediaAsset.kind == MediaAssetKind.VIDEO
        )
    )
    return list(result.scalars().all())