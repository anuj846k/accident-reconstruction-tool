import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import String, Text, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base
from typing import Optional


class ProjectStatus(str, Enum):
    """Status of the accident analysis project."""
    CREATED = "created"           # Just created, no video yet
    VIDEO_UPLOADED = "uploaded"   # Video uploaded, waiting for processing
    PROCESSING = "processing"     # Video being analyzed
    COMPLETED = "completed"       # Analysis done, report ready
    FAILED = "failed"             # Something went wrong


class Project(Base):
    """
    Accident analysis project.
    
    Flow: User uploads video → Processing → Detection → Report
    """
    __tablename__ = "projects"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # Which user owns this project
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    
    status: Mapped[ProjectStatus] = mapped_column(
        SQLEnum(ProjectStatus),
        default=ProjectStatus.CREATED,
    )
    
    # Video file path (local) or URL (cloud storage)
    video_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    
    # Relationships
    user = relationship("User", back_populates="projects")
    media_assets = relationship("MediaAsset", back_populates="project", cascade="all, delete-orphan")
    ai_summaries = relationship("AISummary", back_populates="project", cascade="all, delete-orphan")
    # detections = relationship("Detection", back_populates="project")
    # report = relationship("Report", back_populates="project")