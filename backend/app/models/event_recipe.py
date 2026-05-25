from sqlalchemy import Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class EventRecipe(Base):
    __tablename__ = "event_recipes"

    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True)
    servings_multiplier: Mapped[float] = mapped_column(Float, default=1.0)

    event: Mapped["Event"] = relationship(back_populates="event_recipes")
    recipe: Mapped["Recipe"] = relationship(back_populates="event_recipes")
