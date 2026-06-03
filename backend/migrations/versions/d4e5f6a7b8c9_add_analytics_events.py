"""add analytics_events table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analytics_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("props", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("event_ref", sa.BigInteger(), nullable=True),
        sa.Column("src_payload", sa.String(length=128), nullable=True),
    )
    op.create_index("ix_analytics_events_ts", "analytics_events", ["ts"])
    op.create_index("ix_analytics_events_user_id", "analytics_events", ["user_id"])
    op.create_index("ix_analytics_events_event_type", "analytics_events", ["event_type"])
    op.create_index("ix_analytics_events_event_ref", "analytics_events", ["event_ref"])


def downgrade() -> None:
    op.drop_index("ix_analytics_events_event_ref", table_name="analytics_events")
    op.drop_index("ix_analytics_events_event_type", table_name="analytics_events")
    op.drop_index("ix_analytics_events_user_id", table_name="analytics_events")
    op.drop_index("ix_analytics_events_ts", table_name="analytics_events")
    op.drop_table("analytics_events")
