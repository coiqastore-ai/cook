from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    guests_count: Mapped[int] = mapped_column(Integer, default=1)
    notes: Mapped[str | None] = mapped_column(Text)

    event_recipes: Mapped[list["EventRecipe"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    shopping_items: Mapped[list["ShoppingItem"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    timeline_tasks: Mapped[list["TimelineTask"]] = relationship(back_populates="event", cascade="all, delete-orphan")
