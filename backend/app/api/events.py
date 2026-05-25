from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import Event, EventRecipe, Recipe
from app.schemas.event import (
    AddRecipeToEvent,
    EventCreate,
    EventOut,
    EventUpdate,
    UpdateRecipeMultiplier,
)

router = APIRouter(prefix="/events", tags=["events"])

_EVENT_LOAD = [
    selectinload(Event.event_recipes).selectinload(EventRecipe.recipe).selectinload(Recipe.ingredients)
]


async def _get_event_or_404(event_id: int, session: AsyncSession) -> Event:
    result = await session.execute(
        select(Event).where(Event.id == event_id).options(*_EVENT_LOAD)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    return event


@router.get("/", response_model=list[EventOut])
async def list_events(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Event).options(*_EVENT_LOAD).order_by(Event.date.asc().nulls_last())
    )
    return result.scalars().all()


@router.post("/", response_model=EventOut, status_code=201)
async def create_event(body: EventCreate, session: AsyncSession = Depends(get_session)):
    event = Event(**body.model_dump())
    session.add(event)
    await session.commit()
    return await _get_event_or_404(event.id, session)


@router.get("/{event_id}", response_model=EventOut)
async def get_event(event_id: int, session: AsyncSession = Depends(get_session)):
    return await _get_event_or_404(event_id, session)


@router.patch("/{event_id}", response_model=EventOut)
async def update_event(event_id: int, body: EventUpdate, session: AsyncSession = Depends(get_session)):
    event = await _get_event_or_404(event_id, session)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(event, field, value)
    await session.commit()
    return await _get_event_or_404(event_id, session)


@router.delete("/{event_id}", status_code=204)
async def delete_event(event_id: int, session: AsyncSession = Depends(get_session)):
    event = await _get_event_or_404(event_id, session)
    await session.delete(event)
    await session.commit()


@router.post("/{event_id}/recipes", response_model=EventOut, status_code=201)
async def add_recipe_to_event(
    event_id: int, body: AddRecipeToEvent, session: AsyncSession = Depends(get_session)
):
    await _get_event_or_404(event_id, session)

    # Check recipe exists
    recipe = await session.get(Recipe, body.recipe_id)
    if not recipe:
        raise HTTPException(404, "Recipe not found")

    # Upsert
    existing = await session.get(EventRecipe, (event_id, body.recipe_id))
    if existing:
        existing.servings_multiplier = body.servings_multiplier
    else:
        session.add(EventRecipe(event_id=event_id, recipe_id=body.recipe_id, servings_multiplier=body.servings_multiplier))

    await session.commit()
    return await _get_event_or_404(event_id, session)


@router.patch("/{event_id}/recipes/{recipe_id}", response_model=EventOut)
async def update_recipe_multiplier(
    event_id: int, recipe_id: int, body: UpdateRecipeMultiplier, session: AsyncSession = Depends(get_session)
):
    er = await session.get(EventRecipe, (event_id, recipe_id))
    if not er:
        raise HTTPException(404, "Recipe not linked to this event")
    er.servings_multiplier = body.servings_multiplier
    await session.commit()
    return await _get_event_or_404(event_id, session)


@router.delete("/{event_id}/recipes/{recipe_id}", response_model=EventOut)
async def remove_recipe_from_event(
    event_id: int, recipe_id: int, session: AsyncSession = Depends(get_session)
):
    er = await session.get(EventRecipe, (event_id, recipe_id))
    if not er:
        raise HTTPException(404, "Recipe not linked to this event")
    await session.delete(er)
    await session.commit()
    return await _get_event_or_404(event_id, session)


@router.get("/{event_id}/ical")
async def event_ical(event_id: int, session: AsyncSession = Depends(get_session)):
    """Download event as .ics file — works with Google Calendar, Apple Calendar, Outlook etc."""
    event = await session.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Event not found")
    if not event.date:
        raise HTTPException(422, "Event has no date set")

    dt_start = event.date if event.date.tzinfo else event.date.replace(tzinfo=timezone.utc)
    dt_end = dt_start + timedelta(hours=3)  # 3-hour default duration
    dt_stamp = datetime.now(timezone.utc)
    fmt = "%Y%m%dT%H%M%SZ"

    description = []
    if event.guests_count:
        description.append(f"Гостей: {event.guests_count}")
    if event.notes:
        description.append(event.notes)
    description.append("Открыть в Mealie: https://cook.coiqa.ru")
    desc_text = "\\n".join(description)

    ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Mealie Bot//RU\r\n"
        "CALSCALE:GREGORIAN\r\n"
        "METHOD:PUBLISH\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:mealie-event-{event.id}-{uuid4().hex[:8]}@cook.coiqa.ru\r\n"
        f"DTSTAMP:{dt_stamp.strftime(fmt)}\r\n"
        f"DTSTART:{dt_start.astimezone(timezone.utc).strftime(fmt)}\r\n"
        f"DTEND:{dt_end.astimezone(timezone.utc).strftime(fmt)}\r\n"
        f"SUMMARY:{event.title}\r\n"
        f"DESCRIPTION:{desc_text}\r\n"
        "BEGIN:VALARM\r\n"
        "TRIGGER:-P1D\r\n"
        "ACTION:DISPLAY\r\n"
        f"DESCRIPTION:Завтра — {event.title}\r\n"
        "END:VALARM\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )

    safe_title = "".join(c if c.isalnum() else "_" for c in event.title)[:50]
    return Response(
        content=ics,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}.ics"'},
    )
