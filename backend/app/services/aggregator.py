"""Aggregate ingredients from all event recipes into a shopping list."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Event, EventRecipe, Ingredient, Recipe, ShoppingItem
from app.services import llm


async def aggregate_shopping(event_id: int, session: AsyncSession) -> list[ShoppingItem]:
    # Load event with recipes and their ingredients
    result = await session.execute(
        select(EventRecipe)
        .where(EventRecipe.event_id == event_id)
        .options(
            selectinload(EventRecipe.recipe).selectinload(Recipe.ingredients)
        )
    )
    event_recipes = result.scalars().all()

    # Collect raw totals: name → total_grams
    raw: dict[str, float] = {}
    for er in event_recipes:
        mult = er.servings_multiplier
        for ing in er.recipe.ingredients:
            if ing.normalized_grams is not None:
                raw[ing.name] = raw.get(ing.name, 0.0) + ing.normalized_grams * mult

    if not raw:
        # Clear existing items and return empty
        await session.execute(
            select(ShoppingItem).where(ShoppingItem.event_id == event_id)
        )
        existing = (await session.execute(
            select(ShoppingItem).where(ShoppingItem.event_id == event_id)
        )).scalars().all()
        for item in existing:
            await session.delete(item)
        await session.commit()
        return []

    # Normalize ingredient names via LLM grouping
    grouped = await _group_names(list(raw.keys()))
    # grouped: {canonical_name: [original_names]}

    canonical_totals: dict[str, float] = {}
    for canonical, originals in grouped.items():
        total = sum(raw.get(orig, 0.0) for orig in originals)
        canonical_totals[canonical] = total

    # Delete old items for this event
    existing = (await session.execute(
        select(ShoppingItem).where(ShoppingItem.event_id == event_id)
    )).scalars().all()
    for item in existing:
        await session.delete(item)

    # Create new items
    items = []
    for name, grams in sorted(canonical_totals.items()):
        display = _grams_to_display(grams)
        item = ShoppingItem(
            event_id=event_id,
            ingredient_name=name,
            total_grams=round(grams, 1),
            total_display=display,
            bought=False,
        )
        session.add(item)
        items.append(item)

    await session.commit()
    for item in items:
        await session.refresh(item)
    return items


async def _group_names(names: list[str]) -> dict[str, list[str]]:
    """Ask LLM to group ingredient names by canonical form."""
    if not names:
        return {}
    prompt = f"""Group these ingredient names by canonical form (e.g. "мука пшеничная" and "мука в/с" both map to "мука").
Return JSON object where keys are canonical names and values are arrays of original names.

Names: {names}"""
    try:
        result = await llm.fast_json(prompt)
        if isinstance(result, dict):
            return result
    except Exception:
        pass
    # Fallback: each name is its own group
    return {name: [name] for name in names}


def _grams_to_display(grams: float) -> str:
    if grams >= 1000:
        kg = grams / 1000
        return f"{int(kg)} кг" if kg == int(kg) else f"{kg:.2f} кг"
    return f"{grams:.0f} г"
