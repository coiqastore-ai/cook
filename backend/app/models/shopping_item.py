from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ShoppingItem(Base):
    __tablename__ = "shopping_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    ingredient_name: Mapped[str] = mapped_column(String(500), nullable=False)
    total_grams: Mapped[float | None] = mapped_column(Float)
    total_display: Mapped[str | None] = mapped_column(String(200))
    bought: Mapped[bool] = mapped_column(Boolean, default=False)

    event: Mapped["Event"] = relationship(back_populates="shopping_items")
