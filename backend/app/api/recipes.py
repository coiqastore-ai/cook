from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import Ingredient, Recipe
from app.schemas.recipe import ImportRecipeRequest, RecipeOut, IngredientOut
from app.services import normalizer, recipe_parser

router = APIRouter(prefix="/recipes", tags=["recipes"])


class ImportTextRequest(BaseModel):
    text: str
    title: str | None = None


class ImportImageRequest(BaseModel):
    image_base64: str  # raw base64 or "data:image/...;base64,..." data URL
    title: str | None = None


class IngredientCreate(BaseModel):
    name: str
    quantity: float | None = None
    unit: str | None = None


class IngredientUpdate(BaseModel):
    name: str | None = None
    quantity: float | None = None
    unit: str | None = None


class RecipeCreate(BaseModel):
    title: str
    source_url: str | None = None
    base_servings: int = 4
    cook_time_min: int | None = None
    prep_time_min: int | None = None
    instructions: list[str] = []


class RecipeUpdate(BaseModel):
    title: str | None = None
    source_url: str | None = None
    base_servings: int | None = None
    cook_time_min: int | None = None
    prep_time_min: int | None = None
    instructions: list[str] | None = None


# ---------- READ ----------

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


# ---------- IMPORT ----------

async def _save_parsed_recipe(data: dict, session: AsyncSession) -> Recipe:
    recipe = Recipe(
        title=data["title"],
        source_url=data.get("source_url"),
        base_servings=data.get("base_servings", 4),
        instructions=data.get("instructions"),
        cook_time_min=data.get("cook_time_min"),
        prep_time_min=data.get("prep_time_min"),
    )
    session.add(recipe)
    await session.flush()

    structured = data.get("ingredients_structured") or []
    if not structured and data.get("ingredients_raw"):
        structured = await recipe_parser.parse_ingredients_text(data["ingredients_raw"])

    for ing_data in structured:
        name = (ing_data.get("name") or "").strip()
        if not name:
            continue
        qty = ing_data.get("quantity")
        unit = ing_data.get("unit")
        qty_float = float(qty) if qty is not None else None
        norm_g = await normalizer.normalize_ingredient(name, qty_float, unit)
        session.add(Ingredient(
            recipe_id=recipe.id, name=name, quantity=qty_float, unit=unit, normalized_grams=norm_g,
        ))

    await session.commit()

    result = await session.execute(
        select(Recipe).where(Recipe.id == recipe.id).options(selectinload(Recipe.ingredients))
    )
    return result.scalar_one()


@router.post("/import", response_model=RecipeOut, status_code=201)
async def import_recipe(body: ImportRecipeRequest, session: AsyncSession = Depends(get_session)):
    try:
        data = await recipe_parser.parse_recipe(body.url)
    except Exception as e:
        raise HTTPException(422, f"Failed to parse recipe: {e}")
    return await _save_parsed_recipe(data, session)


@router.post("/import-text", response_model=RecipeOut, status_code=201)
async def import_recipe_from_text(body: ImportTextRequest, session: AsyncSession = Depends(get_session)):
    if not body.text.strip():
        raise HTTPException(422, "Empty text")
    try:
        data = await recipe_parser.parse_recipe_from_text(body.text, title_hint=body.title)
    except Exception as e:
        raise HTTPException(422, f"Failed to parse recipe: {e}")
    return await _save_parsed_recipe(data, session)


@router.post("/import-image", response_model=RecipeOut, status_code=201)
async def import_recipe_from_image(body: ImportImageRequest, session: AsyncSession = Depends(get_session)):
    if not body.image_base64.strip():
        raise HTTPException(422, "Empty image")
    try:
        data = await recipe_parser.parse_recipe_from_image(body.image_base64, title_hint=body.title)
    except Exception as e:
        raise HTTPException(422, f"Failed to parse recipe from image: {e}")
    return await _save_parsed_recipe(data, session)


# ---------- MANUAL CREATE / UPDATE ----------

@router.post("/", response_model=RecipeOut, status_code=201)
async def create_recipe(body: RecipeCreate, session: AsyncSession = Depends(get_session)):
    recipe = Recipe(**body.model_dump())
    session.add(recipe)
    await session.commit()
    result = await session.execute(
        select(Recipe).where(Recipe.id == recipe.id).options(selectinload(Recipe.ingredients))
    )
    return result.scalar_one()


@router.patch("/{recipe_id}", response_model=RecipeOut)
async def update_recipe(recipe_id: int, body: RecipeUpdate, session: AsyncSession = Depends(get_session)):
    recipe = await session.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(404, "Recipe not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(recipe, field, value)
    await session.commit()
    result = await session.execute(
        select(Recipe).where(Recipe.id == recipe.id).options(selectinload(Recipe.ingredients))
    )
    return result.scalar_one()


@router.delete("/{recipe_id}", status_code=204)
async def delete_recipe(recipe_id: int, session: AsyncSession = Depends(get_session)):
    recipe = await session.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(404, "Recipe not found")
    await session.delete(recipe)
    await session.commit()


# ---------- INGREDIENTS (manual edit) ----------

@router.post("/{recipe_id}/ingredients", response_model=IngredientOut, status_code=201)
async def add_ingredient(recipe_id: int, body: IngredientCreate, session: AsyncSession = Depends(get_session)):
    recipe = await session.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(404, "Recipe not found")
    norm_g = await normalizer.normalize_ingredient(body.name, body.quantity, body.unit)
    ing = Ingredient(
        recipe_id=recipe_id, name=body.name, quantity=body.quantity, unit=body.unit, normalized_grams=norm_g,
    )
    session.add(ing)
    await session.commit()
    await session.refresh(ing)
    return ing


@router.patch("/{recipe_id}/ingredients/{ingredient_id}", response_model=IngredientOut)
async def update_ingredient(recipe_id: int, ingredient_id: int, body: IngredientUpdate, session: AsyncSession = Depends(get_session)):
    ing = await session.get(Ingredient, ingredient_id)
    if not ing or ing.recipe_id != recipe_id:
        raise HTTPException(404, "Ingredient not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(ing, field, value)
    # Re-normalize if name/quantity/unit changed
    ing.normalized_grams = await normalizer.normalize_ingredient(ing.name, ing.quantity, ing.unit)
    await session.commit()
    await session.refresh(ing)
    return ing


@router.delete("/{recipe_id}/ingredients/{ingredient_id}", status_code=204)
async def delete_ingredient(recipe_id: int, ingredient_id: int, session: AsyncSession = Depends(get_session)):
    ing = await session.get(Ingredient, ingredient_id)
    if not ing or ing.recipe_id != recipe_id:
        raise HTTPException(404, "Ingredient not found")
    await session.delete(ing)
    await session.commit()
