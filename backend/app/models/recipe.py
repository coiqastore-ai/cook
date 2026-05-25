from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2000))
    base_servings: Mapped[int] = mapped_column(Integer, default=4)
    instructions: Mapped[list | None] = mapped_column(JSONB)
    cook_time_min: Mapped[int | None] = mapped_column(Integer)
    prep_time_min: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Owner — recipe is private to this Telegram user (null = legacy/orphan)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)

    ingredients: Mapped[list["Ingredient"]] = relationship(back_populates="recipe", cascade="all, delete-orphan")
    event_recipes: Mapped[list["EventRecipe"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", passive_deletes=True,
    )
