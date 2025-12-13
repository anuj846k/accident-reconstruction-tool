"""
Database models.

Import all models here so Alembic can discover them.
"""

from src.models.user import User
from src.models.project import Project, ProjectStatus
from src.models.media_asset import MediaAsset, MediaAssetKind, ProcessingStatus
from src.models.detection import Detection, ProcessingRun
from src.models.ai_summary import AISummary

__all__ = [
    "User",
    "Project",
    "ProjectStatus",
    "MediaAsset",
    "MediaAssetKind",
    "ProcessingStatus",
    "Detection",
    "ProcessingRun",
    "AISummary",
]