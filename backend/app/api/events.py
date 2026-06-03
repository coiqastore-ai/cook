from datetime import datetime, timedelta, timezone
from uuid import uuid4

from html import escape

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user_id, get_current_user_id_optional
from app.db import get_session
from app.models import Event, EventCollaborator, EventRecipe, Recipe
from app.services.analytics import track
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


async def _can_access_event(event: Event, user_id: int) -> bool:
    """User can access an event if they own it or are a collaborator."""
    if event.telegram_user_id == user_id:
        return True
    return any(c.telegram_user_id == user_id for c in (event.collaborators or []))


@router.get("/", response_model=list[EventOut])
async def list_events(
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """List events visible to the authenticated user (owned + collaborator-on)."""
    from sqlalchemy import or_

    collab_event_ids = select(EventCollaborator.event_id).where(
        EventCollaborator.telegram_user_id == user_id
    )
    query = (
        select(Event)
        .where(or_(Event.telegram_user_id == user_id, Event.id.in_(collab_event_ids)))
        .options(*_EVENT_LOAD)
        .order_by(Event.date.asc().nulls_last())
    )
    result = await session.execute(query)
    return result.scalars().all()


@router.post("/", response_model=EventOut, status_code=201)
async def create_event(
    body: EventCreate,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    # K-factor detection (read state BEFORE creating this event):
    #  - prior_owned == 0  → this is the user's first owned event
    #  - has_joined        → user already joined someone else's event as a guest
    # both true  → a guest converted into an organizer (the viral loop closed)
    prior_owned = await session.scalar(
        select(func.count()).select_from(Event).where(Event.telegram_user_id == user_id)
    )
    has_joined = await session.scalar(
        select(func.count())
        .select_from(EventCollaborator)
        .where(EventCollaborator.telegram_user_id == user_id)
    )

    data = body.model_dump()
    data["telegram_user_id"] = user_id  # owner = authenticated user
    event = Event(**data)
    session.add(event)
    await session.commit()

    await track(user_id, "event_created", props={"event_id": event.id}, event_ref=event.id)
    if (prior_owned or 0) == 0 and (has_joined or 0) > 0:
        await track(
            user_id, "guest_became_organizer",
            props={"event_id": event.id}, event_ref=event.id,
        )

    return await _get_event_or_404(event.id, session)


async def _require_event_access(event_id: int, user_id: int, session: AsyncSession) -> Event:
    event = await _get_event_or_404(event_id, session)
    if not await _can_access_event(event, user_id):
        raise HTTPException(403, "Forbidden — not your event")
    return event


async def _require_event_owner(event_id: int, user_id: int, session: AsyncSession) -> Event:
    event = await _get_event_or_404(event_id, session)
    if event.telegram_user_id != user_id:
        raise HTTPException(403, "Forbidden — owner-only action")
    return event


@router.get("/{event_id}", response_model=EventOut)
async def get_event(
    event_id: int,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    return await _require_event_access(event_id, user_id, session)


@router.patch("/{event_id}", response_model=EventOut)
async def update_event(
    event_id: int,
    body: EventUpdate,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    event = await _require_event_access(event_id, user_id, session)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(event, field, value)
    await session.commit()
    return await _get_event_or_404(event_id, session)


@router.delete("/{event_id}", status_code=204)
async def delete_event(
    event_id: int,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    event = await _require_event_owner(event_id, user_id, session)
    await session.delete(event)
    await session.commit()


@router.post("/{event_id}/recipes", response_model=EventOut, status_code=201)
async def add_recipe_to_event(
    event_id: int,
    body: AddRecipeToEvent,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    await _require_event_access(event_id, user_id, session)
    recipe = await session.get(Recipe, body.recipe_id)
    if not recipe:
        raise HTTPException(404, "Recipe not found")
    existing = await session.get(EventRecipe, (event_id, body.recipe_id))
    if existing:
        existing.servings_multiplier = body.servings_multiplier
    else:
        session.add(EventRecipe(event_id=event_id, recipe_id=body.recipe_id, servings_multiplier=body.servings_multiplier))
    await session.commit()
    return await _get_event_or_404(event_id, session)


@router.patch("/{event_id}/recipes/{recipe_id}", response_model=EventOut)
async def update_recipe_multiplier(
    event_id: int,
    recipe_id: int,
    body: UpdateRecipeMultiplier,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    await _require_event_access(event_id, user_id, session)
    er = await session.get(EventRecipe, (event_id, recipe_id))
    if not er:
        raise HTTPException(404, "Recipe not linked to this event")
    er.servings_multiplier = body.servings_multiplier
    await session.commit()
    return await _get_event_or_404(event_id, session)


@router.delete("/{event_id}/recipes/{recipe_id}", response_model=EventOut)
async def remove_recipe_from_event(
    event_id: int,
    recipe_id: int,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    await _require_event_access(event_id, user_id, session)
    er = await session.get(EventRecipe, (event_id, recipe_id))
    if not er:
        raise HTTPException(404, "Recipe not linked to this event")
    await session.delete(er)
    await session.commit()
    return await _get_event_or_404(event_id, session)


@router.get("/{event_id}/ical")
async def event_ical(
    event_id: int,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Download event as .ics file — works with Google Calendar, Apple Calendar, Outlook etc."""
    event = await _require_event_access(event_id, user_id, session)
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
    description.append("Открыть в Поляне: https://cook.coiqa.ru")
    desc_text = "\\n".join(description)

    ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Polyana Bot//RU\r\n"
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
    event_id: int,
    body: AddCollaborator,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Two valid cases:
      1. Authenticated user adds *themselves* (deep-link join from bot)
      2. Event owner adds someone else
    """
    event = await _get_event_or_404(event_id, session)
    is_owner = event.telegram_user_id == user_id
    is_self_add = body.telegram_user_id == user_id
    if not (is_owner or is_self_add):
        raise HTTPException(403, "Can only add yourself; only owner can add others")

    existing = await session.get(EventCollaborator, (event_id, body.telegram_user_id))
    was_new = existing is None
    if existing:
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

    # Viral loop: a guest joined someone else's event via deep-link (first time only)
    if was_new and is_self_add and not is_owner:
        await track(
            user_id, "guest_joined",
            props={"event_id": event_id, "owner_id": event.telegram_user_id},
            event_ref=event_id,
        )

    return await _get_event_or_404(event_id, session)


@router.delete("/{event_id}/collaborators/{telegram_user_id}", response_model=EventOut)
async def remove_collaborator(
    event_id: int,
    telegram_user_id: int,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Owner can remove any collaborator. Collaborator can remove themselves (leave)."""
    event = await _get_event_or_404(event_id, session)
    is_owner = event.telegram_user_id == user_id
    is_self_remove = telegram_user_id == user_id
    if not (is_owner or is_self_remove):
        raise HTTPException(403, "Forbidden")

    collab = await session.get(EventCollaborator, (event_id, telegram_user_id))
    if not collab:
        raise HTTPException(404, "Collaborator not found")
    await session.delete(collab)
    await session.commit()
    return await _get_event_or_404(event_id, session)


@router.get("/{event_id}/menu.pdf")
async def event_menu_pdf(
    event_id: int,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Generate beautiful PDF menu for sharing with guests (no ingredients/grams)."""
    from app.services.pdf_menu import render_menu_pdf

    event = await _require_event_access(event_id, user_id, session)
    pdf_bytes = render_menu_pdf(event)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="menu-{event.id}.pdf"'},
    )


# ---------------------------------------------------------------------------
# Share-card endpoints — for rich Telegram link previews
# ---------------------------------------------------------------------------

BOT_USERNAME = "reciptesbot"
PUBLIC_HOST = "https://cook.coiqa.ru"


@router.get("/{event_id}/share", response_class=HTMLResponse)
async def share_event_html(event_id: int, session: AsyncSession = Depends(get_session)):
    """Public HTML page with OpenGraph tags. Telegram crawler fetches this and renders preview card.
    Visiting in a browser → auto-redirect to bot deep-link to join the event."""
    event = await _get_event_or_404(event_id, session)
    deep_link = f"https://t.me/{BOT_USERNAME}?start=event_{event_id}"
    cover_url = f"{PUBLIC_HOST}/api/events/{event_id}/share/cover.png"
    share_url = f"{PUBLIC_HOST}/api/events/{event_id}/share"

    parts: list[str] = []
    if event.date:
        parts.append(event.date.strftime("%d.%m.%Y"))
    parts.append(f"{event.guests_count} гостей")
    n = len(event.event_recipes)
    parts.append(f"{n} {'блюдо' if n == 1 else ('блюда' if n < 5 else 'блюд')}")
    desc = " · ".join(parts)

    title_esc = escape(event.title)
    desc_esc = escape(desc)

    html = f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_esc} — Поляна</title>

<meta property="og:title" content="{title_esc}">
<meta property="og:description" content="{desc_esc}">
<meta property="og:image" content="{cover_url}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="{share_url}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Поляна">

<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title_esc}">
<meta name="twitter:description" content="{desc_esc}">
<meta name="twitter:image" content="{cover_url}">

<meta http-equiv="refresh" content="0; url={deep_link}">
<style>
body{{font-family:system-ui,sans-serif;background:#fafaf7;color:#2c2c2c;text-align:center;padding:40px 20px;margin:0}}
h1{{font-weight:300;font-size:32px;margin:20px 0}}
.btn{{display:inline-block;background:#22c55e;color:#fff;padding:14px 28px;border-radius:12px;text-decoration:none;font-weight:500;margin-top:20px}}
</style>
</head>
<body>
<p style="color:#b8956c;letter-spacing:6px;font-size:13px">МЕНЮ В ПОЛЯНЕ</p>
<h1>{title_esc}</h1>
<p style="color:#6c6c6c">{desc_esc}</p>
<p><a href="{deep_link}" class="btn">📲 Открыть в Telegram</a></p>
<script>
// Programmatic redirect (faster than meta-refresh on most browsers)
setTimeout(function() {{ window.location.href = "{deep_link}"; }}, 100);
</script>
</body>
</html>"""
    return HTMLResponse(content=html)


@router.get("/{event_id}/share/cover.png")
async def share_event_cover(event_id: int, session: AsyncSession = Depends(get_session)):
    """Generated PNG used as og:image in Telegram link preview."""
    from app.services.share_card import render_cover_png

    event = await _get_event_or_404(event_id, session)
    png = render_cover_png(event)
    return Response(
        content=png,
        media_type="image/png",
        headers={
            # Telegram caches og:image — let it cache for a while
            "Cache-Control": "public, max-age=3600",
        },
    )
