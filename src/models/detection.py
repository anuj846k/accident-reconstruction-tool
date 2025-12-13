import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Float, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class Detection(Base):
    """Individual vehicle detection from video processing."""
    __tablename__ = "detections"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    
    frame_idx: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Frame number in the video",
        index=True,
    )
    
    timestamp_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Timestamp in milliseconds",
    )
    
    track_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Tracking ID assigned by ByteTrack",
        index=True,
    )
    
    class_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Detected class (car, truck, etc.)",
    )
    
    class_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="YOLO class ID",
    )
    
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Detection confidence score",
    )
    
    bbox_x: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Top-left X coordinate",
    )
    
    bbox_y: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Top-left Y coordinate",
    )
    
    bbox_w: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Bounding box width",
    )
    
    bbox_h: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Bounding box height",
    )
    
    center_x: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Center X coordinate",
    )
    
    center_y: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Center Y coordinate",
    )
    
    speed_mph: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Estimated speed in mph",
    )
    
    world_x: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="World X coordinate (meters)",
    )
    
    world_y: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="World Y coordinate (meters)",
    )
    
    extra: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Additional detection metadata",
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
    
    # Relationships
    # project = relationship("Project", back_populates="detections")
    
    __table_args__ = (
        Index("ix_detections_project_frame", "project_id", "frame_idx"),
        Index("ix_detections_project_track", "project_id", "track_id"),
    )


class ProcessingRun(Base):
    """Metadata for a video processing job."""
    __tablename__ = "processing_runs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="pending, processing, completed, failed",
    )
    
    video_uri: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Cloudinary video URL",
    )
    
    total_frames: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Total frames in video",
    )
    
    processed_frames: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Frames processed so far",
    )
    
    detection_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Total detections found",
    )
    
    unique_tracks: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Unique vehicles tracked",
    )
    
    config: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Processing configuration used",
    )
    
    error_message: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True,
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
    
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Relationships
    # project = relationship("Project", back_populates="processing_runs")
    # detections = relationship("Detection", back_populates="run", cascade="all, delete-orphan")

