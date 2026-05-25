"""add event reminder fields

Revision ID: a1b2c3d4e5f6
Revises: b27b6a5aa7ca
Create Date: 2026-05-25 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "b27b6a5aa7ca"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("events", sa.Column("telegram_user_id", sa.BigInteger(), nullable=True))
    op.add_column("events", sa.Column("reminder_sent", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("events", "reminder_sent")
    op.drop_column("events", "telegram_user_id")
