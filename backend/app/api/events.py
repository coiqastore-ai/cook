from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import Event, EventCollaborator, EventRecipe, Recipe
from app.schemas.event import (
    AddCollaborator,
    AddRecipeToEvent,
    CollaboratorOut,
    EventCreate,
    EventOut,
    EventUpdate,
    UpdateRecipeMultiplier,
)

router = APIRouter(prefix="/events", tags=["events"])

_EVENT_LOAD = [
    selectinload(Event.event_recipes).selectinload(EventRecipe.recipe).selectinload(Recipe.ingredients),
    selectinload(Event.collaborators),
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
async def list_events(
    telegram_user_id: int | None = None,
    session: AsyncSession = Depends(get_session),
):
    """List events. If telegram_user_id is provided, only return events the user owns
    or is collaborator on. Otherwise return all (admin view)."""
    from sqlalchemy import or_

    query = select(Event).options(*_EVENT_LOAD).order_by(Event.date.asc().nulls_last())
    if telegram_user_id is not None:
        # Owned OR collaborator-on
        collab_event_ids = select(EventCollaborator.event_id).where(
            EventCollaborator.telegram_user_id == telegram_user_id
        )
        query = query.where(
            or_(Event.telegram_user_id == telegram_user_id, Event.id.in_(collab_event_ids))
        )
    result = await session.execute(query)
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

    # ASCII filename for the header (HTTP headers must be latin-1);
    # full Russian title is preserved inside the .ics SUMMARY.
    return Response(
        content=ics,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="event-{event.id}.ics"'},
    )


@router.post("/{event_id}/collaborators", response_model=EventOut, status_code=201)
async def add_collaborator(
    event_id: int, body: AddCollaborator, session: AsyncSession = Depends(get_session)
):
    await _get_event_or_404(event_id, session)
    existing = await session.get(EventCollaborator, (event_id, body.telegram_user_id))
    if existing:
        # Update name/username if changed
        if body.name:
            existing.name = body.name
        if body.username:
            existing.username = body.username
    else:
        session.add(EventCollaborator(
            event_id=event_id,
            telegram_user_id=body.telegram_user_id,
            name=body.name,
            username=body.username,
        ))
    await session.commit()
    return await _get_event_or_404(event_id, session)


@router.delete("/{event_id}/collaborators/{telegram_user_id}", response_model=EventOut)
async def remove_collaborator(
    event_id: int, telegram_user_id: int, session: AsyncSession = Depends(get_session)
):
    collab = await session.get(EventCollaborator, (event_id, telegram_user_id))
    if not collab:
        raise HTTPException(404, "Collaborator not found")
    await session.delete(collab)
    await session.commit()
    return await _get_event_or_404(event_id, session)


@router.get("/{event_id}/menu.pdf")
async def event_menu_pdf(event_id: int, session: AsyncSession = Depends(get_session)):
    """Generate beautiful PDF menu for sharing with guests (no ingredients/grams)."""
    from app.services.pdf_menu import render_menu_pdf

    event = await _get_event_or_404(event_id, session)
    pdf_bytes = render_menu_pdf(event)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="menu-{event.id}.pdf"'},
    )
