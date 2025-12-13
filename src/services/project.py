import uuid
from typing import Optional, List, Tuple
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.project import Project, ProjectStatus


# --- Pydantic Schemas ---

class ProjectCreate(BaseModel):
    """Schema for creating a project."""
    title: str
    description: Optional[str] = None


class ProjectUpdate(BaseModel):
    """Schema for updating a project."""
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[ProjectStatus] = None


class ProjectPublic(BaseModel):
    """Schema for returning project data."""
    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    description: Optional[str] = None
    status: ProjectStatus
    video_path: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProjectsPublic(BaseModel):
    """Schema for returning list of projects."""
    data: List[ProjectPublic]
    count: int


# --- CRUD Functions ---

async def create_project(
    session: AsyncSession,
    project_create: ProjectCreate,
    user_id: uuid.UUID
) -> Project:
    """Create a new project."""
    project = Project(
        title=project_create.title,
        description=project_create.description,
        user_id=user_id,
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def get_project(
    session: AsyncSession,
    project_id: uuid.UUID,
    user_id: uuid.UUID
) -> Optional[Project]:
    """Get a project by ID (only if owned by user)."""
    result = await session.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def list_projects(
    session: AsyncSession,
    user_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100
) -> Tuple[List[Project], int]:
    """List all projects for a user."""
    # Get count
    count_result = await session.execute(
        select(func.count()).select_from(Project).where(Project.user_id == user_id)
    )
    count = count_result.scalar()
    
    # Get projects
    result = await session.execute(
        select(Project)
        .where(Project.user_id == user_id)
        .offset(skip)
        .limit(limit)
        .order_by(Project.created_at.desc())
    )
    projects = list(result.scalars().all())
    
    return projects, count


async def update_project(
    session: AsyncSession,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    project_update: ProjectUpdate
) -> Optional[Project]:
    """Update a project."""
    project = await get_project(session, project_id, user_id)
    if not project:
        return None
    
    update_data = project_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)
    
    await session.commit()
    await session.refresh(project)
    return project


async def delete_project(
    session: AsyncSession,
    project_id: uuid.UUID,
    user_id: uuid.UUID
) -> bool:
    """Delete a project."""
    project = await get_project(session, project_id, user_id)
    if not project:
        return False
    
    await session.delete(project)
    await session.commit()
    return True