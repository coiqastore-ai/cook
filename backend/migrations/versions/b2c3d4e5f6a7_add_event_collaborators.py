"""add event_collaborators table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-25 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "event_collaborators",
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("username", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("event_collaborators")
