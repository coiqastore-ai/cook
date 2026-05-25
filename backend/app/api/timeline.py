from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Event, TimelineTask
from app.schemas.timeline import TimelineTaskOut
from app.services.timeline import generate_timeline

router = APIRouter(prefix="/timeline", tags=["timeline"])


@router.get("/{event_id}", response_model=list[TimelineTaskOut])
async def get_timeline(event_id: int, session: AsyncSession = Depends(get_session)):
    event = await session.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Event not found")
    if not event.date:
        raise HTTPException(422, "Event has no date set — cannot generate timeline")

    # Return cached if exists, otherwise generate
    existing = (await session.execute(
        select(TimelineTask).where(TimelineTask.event_id == event_id).order_by(TimelineTask.offset_hours)
    )).scalars().all()
    if existing:
        return existing

    return await generate_timeline(event_id, event.date, session)


@router.post("/{event_id}/regenerate", response_model=list[TimelineTaskOut])
async def regenerate_timeline(event_id: int, session: AsyncSession = Depends(get_session)):
    event = await session.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Event not found")
    if not event.date:
        raise HTTPException(422, "Event has no date set")
    return await generate_timeline(event_id, event.date, session)
