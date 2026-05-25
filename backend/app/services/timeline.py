"""Generate cooking timeline via LLM."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import EventRecipe, Recipe, TimelineTask
from app.services import llm


async def generate_timeline(event_id: int, event_datetime: datetime, session: AsyncSession) -> list[TimelineTask]:
    # Load recipes for the event
    result = await session.execute(
        select(EventRecipe)
        .where(EventRecipe.event_id == event_id)
        .options(selectinload(EventRecipe.recipe))
    )
    event_recipes = result.scalars().all()

    if not event_recipes:
        return []

    recipes_info = [
        {
            "recipe_id": er.recipe_id,
            "title": er.recipe.title,
            "cook_time_min": er.recipe.cook_time_min,
            "prep_time_min": er.recipe.prep_time_min,
        }
        for er in event_recipes
    ]

    event_time_str = event_datetime.strftime("%Y-%m-%d %H:%M")

    prompt = f"""Create a cooking timeline for a feast. The feast starts at {event_time_str}.

Recipes:
{recipes_info}

Generate a timeline counting backwards from the feast start time.
Return JSON array, each element:
{{
  "recipe_id": number or null,
  "offset_hours": number (negative = before feast, e.g. -2.5 means 2.5 hours before),
  "action": "description of what to do",
  "duration_min": number
}}

Order by offset_hours ascending (most negative first). Include prep, cooking, and final assembly steps."""

    try:
        tasks_data = await llm.smart_json(prompt)
        if not isinstance(tasks_data, list):
            return []
    except Exception:
        return []

    # Delete existing timeline for this event
    existing = (await session.execute(
        select(TimelineTask).where(TimelineTask.event_id == event_id)
    )).scalars().all()
    for task in existing:
        await session.delete(task)

    tasks = []
    for item in tasks_data:
        try:
            task = TimelineTask(
                event_id=event_id,
                recipe_id=item.get("recipe_id"),
                offset_hours=float(item["offset_hours"]),
                action=str(item["action"]),
                duration_min=item.get("duration_min"),
            )
            session.add(task)
            tasks.append(task)
        except (KeyError, TypeError, ValueError):
            continue

    await session.commit()
    for task in tasks:
        await session.refresh(task)
    return tasks
