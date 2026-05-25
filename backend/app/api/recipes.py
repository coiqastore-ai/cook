from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import Ingredient, Recipe
from app.schemas.recipe import ImportRecipeRequest, RecipeOut
from app.services import normalizer, recipe_parser

router = APIRouter(prefix="/recipes", tags=["recipes"])


@router.get("/", response_model=list[RecipeOut])
async def list_recipes(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Recipe).options(selectinload(Recipe.ingredients)).order_by(Recipe.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{recipe_id}", response_model=RecipeOut)
async def get_recipe(recipe_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Recipe).where(Recipe.id == recipe_id).options(selectinload(Recipe.ingredients))
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(404, "Recipe not found")
    return recipe


@router.post("/import", response_model=RecipeOut, status_code=201)
async def import_recipe(body: ImportRecipeRequest, session: AsyncSession = Depends(get_session)):
    try:
        data = await recipe_parser.parse_recipe(body.url)
    except Exception as e:
        raise HTTPException(422, f"Failed to parse recipe: {e}")

    recipe = Recipe(
        title=data["title"],
        source_url=data.get("source_url"),
        base_servings=data.get("base_servings", 4),
        instructions=data.get("instructions"),
        cook_time_min=data.get("cook_time_min"),
        prep_time_min=data.get("prep_time_min"),
    )
    session.add(recipe)
    await session.flush()  # get recipe.id

    # Parse and normalize ingredients
    structured = data.get("ingredients_structured") or []
    if not structured and data.get("ingredients_raw"):
        structured = await recipe_parser.parse_ingredients_text(data["ingredients_raw"])

    for ing_data in structured:
        name = ing_data.get("name", "").strip()
        if not name:
            continue
        qty = ing_data.get("quantity")
        unit = ing_data.get("unit")
        qty_float = float(qty) if qty is not None else None
        norm_g = await normalizer.normalize_ingredient(name, qty_float, unit)
        ing = Ingredient(
            recipe_id=recipe.id,
            name=name,
            quantity=qty_float,
            unit=unit,
            normalized_grams=norm_g,
        )
        session.add(ing)

    await session.commit()
    await session.refresh(recipe)

    result = await session.execute(
        select(Recipe).where(Recipe.id == recipe.id).options(selectinload(Recipe.ingredients))
    )
    return result.scalar_one()
