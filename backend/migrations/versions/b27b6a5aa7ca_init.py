"""init

Revision ID: b27b6a5aa7ca
Revises: 
Create Date: 2026-05-25 12:52:20.325625

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b27b6a5aa7ca'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recipes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("source_url", sa.String(2000), nullable=True),
        sa.Column("base_servings", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("instructions", postgresql.JSONB(), nullable=True),
        sa.Column("cook_time_min", sa.Integer(), nullable=True),
        sa.Column("prep_time_min", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "ingredients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("recipe_id", sa.Integer(), sa.ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(100), nullable=True),
        sa.Column("normalized_grams", sa.Float(), nullable=True),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("guests_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_table(
        "event_recipes",
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("recipe_id", sa.Integer(), sa.ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("servings_multiplier", sa.Float(), nullable=False, server_default="1.0"),
    )
    op.create_table(
        "shopping_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ingredient_name", sa.String(500), nullable=False),
        sa.Column("total_grams", sa.Float(), nullable=True),
        sa.Column("total_display", sa.String(200), nullable=True),
        sa.Column("bought", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_table(
        "timeline_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipe_id", sa.Integer(), sa.ForeignKey("recipes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("offset_hours", sa.Float(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("duration_min", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("timeline_tasks")
    op.drop_table("shopping_items")
    op.drop_table("event_recipes")
    op.drop_table("events")
    op.drop_table("ingredients")
    op.drop_table("recipes")
