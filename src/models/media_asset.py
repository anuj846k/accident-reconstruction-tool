import uuid
from datetime import datetime
from typing import Optional
from enum import Enum

from sqlalchemy import String, Integer, DateTime, ForeignKey, JSON, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class MediaAssetKind(str, Enum):
    """Type of media asset."""
    VIDEO = "video"
    IMAGE = "image"
    FRAME = "frame"


class ProcessingStatus(str, Enum):
    """Processing status of the media."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class MediaAsset(Base):
    """
    Media asset model - stores video/image files.
    
    Each project can have one main video and multiple
    extracted frames or generated images.
    """
    __tablename__ = "media_assets"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    kind: Mapped[MediaAssetKind] = mapped_column(
        SQLEnum(MediaAssetKind),
        default=MediaAssetKind.VIDEO,
    )
    
    # File path (local) or URI (s3://bucket/key)
    uri: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    
    # File size in bytes
    file_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    
    # Original filename
    filename: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    
    # Content type (e.g., video/mp4)
    content_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    
    # Processing status
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        SQLEnum(ProcessingStatus),
        default=ProcessingStatus.PENDING,
    )
    
    # Metadata (fps, duration, width, height, etc.)
    meta: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
    )
    
    # Relationships
    project = relationship("Project", back_populates="media_assets")