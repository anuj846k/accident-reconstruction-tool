import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class HomographySession(Base):
    """Calibration session linking image points to GPS coordinates."""
    __tablename__ = "homography_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # One session per project
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="draft",  # draft, solved
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    solved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    pairs: Mapped[List["HomographyPair"]] = relationship(
        "HomographyPair",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="HomographyPair.order_idx",
    )
    model: Mapped[Optional["HomographyModel"]] = relationship(
        "HomographyModel",
        back_populates="session",
        cascade="all, delete-orphan",
        uselist=False,
    )


class HomographyPair(Base):
    """A single calibration point pair: image pixel → GPS coordinate."""
    __tablename__ = "homography_pairs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("homography_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Image coordinates (normalized 0-1)
    image_x_norm: Mapped[float] = mapped_column(Float, nullable=False)
    image_y_norm: Mapped[float] = mapped_column(Float, nullable=False)
    # GPS coordinates
    map_lat: Mapped[float] = mapped_column(Float, nullable=False)
    map_lng: Mapped[float] = mapped_column(Float, nullable=False)
    # Order for display
    order_idx: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    session: Mapped["HomographySession"] = relationship(
        "HomographySession", back_populates="pairs"
    )


class HomographyModel(Base):
    """Solved homography matrix."""
    __tablename__ = "homography_models"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("homography_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 3x3 matrix stored as JSON [[a,b,c],[d,e,f],[g,h,i]]
    matrix_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    reprojection_error: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    # Relationships
    session: Mapped["HomographySession"] = relationship(
        "HomographySession", back_populates="model"
    )