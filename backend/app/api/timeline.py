from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user_id
from app.db import get_session
from app.models import Event, TimelineTask
from app.schemas.timeline import TimelineTaskOut
from app.services.timeline import generate_timeline

router = APIRouter(prefix="/timeline", tags=["timeline"])


async def _require_event_access(event_id: int, user_id: int, session: AsyncSession) -> Event:
    result = await session.execute(
        select(Event).where(Event.id == event_id).options(selectinload(Event.collaborators))
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    if event.telegram_user_id != user_id and not any(
        c.telegram_user_id == user_id for c in (event.collaborators or [])
    ):
        raise HTTPException(403, "Forbidden — not your event")
    return event


@router.get("/{event_id}", response_model=list[TimelineTaskOut])
async def get_timeline(
    event_id: int,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    event = await _require_event_access(event_id, user_id, session)
    if not event.date:
        raise HTTPException(422, "Event has no date set — cannot generate timeline")

    existing = (await session.execute(
        select(TimelineTask).where(TimelineTask.event_id == event_id).order_by(TimelineTask.offset_hours)
    )).scalars().all()
    if existing:
        return existing

    return await generate_timeline(event_id, event.date, session)


@router.post("/{event_id}/regenerate", response_model=list[TimelineTaskOut])
async def regenerate_timeline(
    event_id: int,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    event = await _require_event_access(event_id, user_id, session)
    if not event.date:
        raise HTTPException(422, "Event has no date set")
    return await generate_timeline(event_id, event.date, session)
