"""merge heads

Revision ID: 9a05a949b6bf
Revises: 6a67b8944114, d1e2f3a4b5c6
Create Date: 2025-12-12 11:39:55.614000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a05a949b6bf'
down_revision: Union[str, None] = ('6a67b8944114', 'd1e2f3a4b5c6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
