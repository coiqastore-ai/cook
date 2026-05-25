"""Aggregate ingredients from all event recipes into a shopping list."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import EventRecipe, Recipe, ShoppingItem
from app.services import llm


async def aggregate_shopping(event_id: int, session: AsyncSession) -> list[ShoppingItem]:
    # Load event recipes with their ingredients
    result = await session.execute(
        select(EventRecipe)
        .where(EventRecipe.event_id == event_id)
        .options(selectinload(EventRecipe.recipe).selectinload(Recipe.ingredients))
    )
    event_recipes = result.scalars().all()

    # Three pools:
    #   weighable — can be summed in grams (after normalization)
    #   countable — has quantity + non-weight unit (шт, головка, зубчик, etc.)
    #   misc      — only a unit string like "по вкусу", no quantity
    weighable: dict[str, float] = {}
    countable: dict[str, dict[str, float]] = {}
    misc: dict[str, str] = {}

    for er in event_recipes:
        mult = er.servings_multiplier
        for ing in er.recipe.ingredients:
            name = ing.name.strip()
            if not name:
                continue

            if ing.normalized_grams is not None:
                weighable[name] = weighable.get(name, 0.0) + ing.normalized_grams * mult
            elif ing.quantity is not None:
                unit_key = (ing.unit or "шт").strip().lower()
                countable.setdefault(name, {})
                countable[name][unit_key] = countable[name].get(unit_key, 0.0) + ing.quantity * mult
            elif ing.unit:
                misc[name] = ing.unit  # e.g. "по вкусу"
            else:
                misc[name] = "—"

    # --- Clear existing shopping items for this event ---
    existing = (await session.execute(
        select(ShoppingItem).where(ShoppingItem.event_id == event_id)
    )).scalars().all()
    for item in existing:
        await session.delete(item)

    items: list[ShoppingItem] = []

    # --- Weighable: group canonical names via LLM, sum grams ---
    if weighable:
        grouped = await _group_names(list(weighable.keys()))
        canonical_totals: dict[str, float] = {}
        for canonical, originals in grouped.items():
            total = sum(weighable.get(orig, 0.0) for orig in originals)
            canonical_totals[canonical] = total

        for name, grams in sorted(canonical_totals.items()):
            item = ShoppingItem(
                event_id=event_id,
                ingredient_name=name,
                total_grams=round(grams, 1),
                total_display=_grams_to_display(grams),
                bought=False,
            )
            session.add(item)
            items.append(item)

    # --- Countable (3 шт, 2 зубчика etc) — sum per unit, no LLM grouping ---
    for name, units in sorted(countable.items()):
        parts = []
        for unit, qty in units.items():
            q = round(qty, 1) if qty != int(qty) else int(qty)
            parts.append(f"{q} {unit}")
        item = ShoppingItem(
            event_id=event_id,
            ingredient_name=name,
            total_grams=None,
            total_display=", ".join(parts),
            bought=False,
        )
        session.add(item)
        items.append(item)

    # --- Misc (соль "по вкусу" etc) — leave note as is ---
    for name, note in sorted(misc.items()):
        item = ShoppingItem(
            event_id=event_id,
            ingredient_name=name,
            total_grams=None,
            total_display=note,
            bought=False,
        )
        session.add(item)
        items.append(item)

    await session.commit()
    for item in items:
        await session.refresh(item)
    return items


async def _group_names(names: list[str]) -> dict[str, list[str]]:
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
    return {name: [name] for name in names}


def _grams_to_display(grams: float) -> str:
    if grams >= 1000:
        kg = grams / 1000
        return f"{int(kg)} кг" if kg == int(kg) else f"{kg:.2f} кг"
    return f"{grams:.0f} г"
