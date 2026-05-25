from sqlalchemy import Float, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class TimelineTask(Base):
    __tablename__ = "timeline_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    recipe_id: Mapped[int | None] = mapped_column(ForeignKey("recipes.id", ondelete="SET NULL"))
    offset_hours: Mapped[float] = mapped_column(Float, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    duration_min: Mapped[int | None] = mapped_column(Integer)

    event: Mapped["Event"] = relationship(back_populates="timeline_tasks")
    recipe: Mapped["Recipe | None"] = relationship()
