"""Add ai_summaries table

Revision ID: d1e2f3a4b5c6
Revises: 8382003b60c1
Create Date: 2025-01-11 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'd1e2f3a4b5c6'
down_revision = '8382003b60c1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create ai_summaries table
    op.create_table(
        'ai_summaries',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('summary_text', sa.Text(), nullable=False),
        sa.Column('severity_assessment', sa.String(50), nullable=True),
        sa.Column('recommendations', sa.Text(), nullable=True),
        sa.Column('collision_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('ai_model', sa.String(100), nullable=True),
        sa.Column('kestra_execution_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create index on project_id for faster lookups
    op.create_index(
        'ix_ai_summaries_project_id',
        'ai_summaries',
        ['project_id'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_ai_summaries_project_id', table_name='ai_summaries')
    op.drop_table('ai_summaries')






