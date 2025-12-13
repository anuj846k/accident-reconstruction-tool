"""
AI Summary Model.

Stores AI-generated collision analysis summaries from Kestra workflows.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.core.database import Base


class AISummary(Base):
    """
    AI-generated collision analysis summary.
    
    Created by Kestra workflow after AI (OpenAI/Claude) analyzes collision data.
    """
    __tablename__ = "ai_summaries"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    
    # AI-generated content
    summary_text = Column(Text, nullable=False)  # Main AI narrative
    severity_assessment = Column(String(50), nullable=True)  # AI's severity rating
    recommendations = Column(Text, nullable=True)  # AI recommendations
    
    # Collision context
    collision_data = Column(JSON, nullable=True)  # Original collision data sent to AI
    
    # Metadata
    ai_model = Column(String(100), nullable=True)  # e.g., "gpt-4o-mini", "claude-3"
    kestra_execution_id = Column(String(255), nullable=True)  # Kestra workflow execution ID
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    project = relationship("Project", back_populates="ai_summaries")
    
    def __repr__(self):
        return f"<AISummary {self.id} for project {self.project_id}>"

