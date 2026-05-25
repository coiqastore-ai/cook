from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class EventCollaborator(Base):
    __tablename__ = "event_collaborators"

    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(200))  # display name
    username: Mapped[str | None] = mapped_column(String(100))  # @username

    event: Mapped["Event"] = relationship(back_populates="collaborators")
