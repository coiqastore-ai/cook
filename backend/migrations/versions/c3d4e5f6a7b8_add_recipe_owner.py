"""add recipe owner (telegram_user_id)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-25 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("recipes", sa.Column("telegram_user_id", sa.BigInteger(), nullable=True))
    op.create_index("ix_recipes_telegram_user_id", "recipes", ["telegram_user_id"])
    # Data migration: assign existing recipes to the owner of any event they're attached to
    op.execute("""
        UPDATE recipes r
        SET telegram_user_id = (
            SELECT e.telegram_user_id
            FROM event_recipes er
            JOIN events e ON e.id = er.event_id
            WHERE er.recipe_id = r.id
              AND e.telegram_user_id IS NOT NULL
            ORDER BY e.id ASC
            LIMIT 1
        )
        WHERE r.telegram_user_id IS NULL;
    """)


def downgrade() -> None:
    op.drop_index("ix_recipes_telegram_user_id", table_name="recipes")
    op.drop_column("recipes", "telegram_user_id")
