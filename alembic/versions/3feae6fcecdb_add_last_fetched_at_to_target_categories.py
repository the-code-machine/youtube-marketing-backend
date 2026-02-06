"""add last_fetched_at to target_categories

Revision ID: 3feae6fcecdb
Revises: 0e1413193bcd
Create Date: 2026-02-06 16:15:24.793671

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3feae6fcecdb'
down_revision: Union[str, Sequence[str], None] = '0e1413193bcd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
