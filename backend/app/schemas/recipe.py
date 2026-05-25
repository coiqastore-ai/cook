from datetime import datetime

from pydantic import BaseModel, HttpUrl


class IngredientOut(BaseModel):
    id: int
    name: str
    quantity: float | None
    unit: str | None
    normalized_grams: float | None

    model_config = {"from_attributes": True}


class RecipeOut(BaseModel):
    id: int
    title: str
    source_url: str | None
    base_servings: int
    instructions: list | None
    cook_time_min: int | None
    prep_time_min: int | None
    created_at: datetime
    telegram_user_id: int | None = None
    ingredients: list[IngredientOut] = []

    model_config = {"from_attributes": True}


class ImportRecipeRequest(BaseModel):
    url: str
    telegram_user_id: int | None = None
