from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AnalyticsEvent(Base):
    """Append-only analytics event log. Server-truth for North Star (K-factor),
    activation and the viral loop. Never read on the hot path — analyzed via SQL."""

    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    # Telegram user id (nullable: some events may be anonymous)
    user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    # event_type: user_start | event_created | guest_joined | guest_became_organizer | ...
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # arbitrary payload (event_id, owner_id, counts, etc.)
    props: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    # denormalized reference to a domain event (events.id) for fast joins/filtering
    event_ref: Mapped[int | None] = mapped_column(BigInteger, index=True)
    # attribution source captured at /start (seed_<x> | event_<id> | organic | ...)
    src_payload: Mapped[str | None] = mapped_column(String(128))
