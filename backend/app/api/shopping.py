from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user_id
from app.db import get_session
from app.models import Event, EventCollaborator, ShoppingItem
from app.schemas.shopping import ShoppingItemOut, ShoppingItemUpdate
from app.services.aggregator import aggregate_shopping

router = APIRouter(prefix="/shopping", tags=["shopping"])


async def _require_event_access(event_id: int, user_id: int, session: AsyncSession) -> Event:
    event = await session.execute(
        select(Event).where(Event.id == event_id).options(selectinload(Event.collaborators))
    )
    event = event.scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    if event.telegram_user_id != user_id and not any(
        c.telegram_user_id == user_id for c in (event.collaborators or [])
    ):
        raise HTTPException(403, "Forbidden — not your event")
    return event


@router.get("/{event_id}", response_model=list[ShoppingItemOut])
async def get_shopping_list(
    event_id: int,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    await _require_event_access(event_id, user_id, session)
    return await aggregate_shopping(event_id, session)


@router.patch("/{event_id}/items/{item_id}", response_model=ShoppingItemOut)
async def toggle_item(
    event_id: int,
    item_id: int,
    body: ShoppingItemUpdate,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    await _require_event_access(event_id, user_id, session)
    item = await session.get(ShoppingItem, item_id)
    if not item or item.event_id != event_id:
        raise HTTPException(404, "Item not found")
    item.bought = body.bought
    await session.commit()
    await session.refresh(item)
    return item


@router.get("/{event_id}/export", response_model=str)
async def export_shopping_text(
    event_id: int,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    event = await _require_event_access(event_id, user_id, session)
    items = (await session.execute(
        select(ShoppingItem).where(ShoppingItem.event_id == event_id).order_by(ShoppingItem.ingredient_name)
    )).scalars().all()
    if not items:
        return "Список закупки пуст"
    lines = [f"Закупка для «{event.title}»:", ""]
    for item in items:
        check = "✅" if item.bought else "☐"
        lines.append(f"{check} {item.ingredient_name} — {item.total_display or '?'}")
    return "\n".join(lines)
