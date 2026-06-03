"""Analytics tracking — fire-and-forget event logging.

Uses an INDEPENDENT DB session so a failed insert can never poison the
business transaction. Swallows all errors: analytics must never break a request.
"""
import logging

from app.db import async_session_factory
from app.models import AnalyticsEvent

log = logging.getLogger(__name__)


async def track(
    user_id: int | None,
    event_type: str,
    props: dict | None = None,
    event_ref: int | None = None,
    src_payload: str | None = None,
) -> None:
    if not event_type:
        return
    try:
        async with async_session_factory() as session:
            session.add(
                AnalyticsEvent(
                    user_id=user_id,
                    event_type=event_type[:64],
                    props=props or {},
                    event_ref=event_ref,
                    src_payload=(src_payload[:128] if src_payload else None),
                )
            )
            await session.commit()
    except Exception:
        log.exception("analytics track failed: %s", event_type)
