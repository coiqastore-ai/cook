from datetime import datetime

from pydantic import BaseModel

from app.schemas.recipe import RecipeOut


class EventRecipeOut(BaseModel):
    recipe_id: int
    servings_multiplier: float
    recipe: RecipeOut

    model_config = {"from_attributes": True}


class CollaboratorOut(BaseModel):
    telegram_user_id: int
    name: str | None
    username: str | None

    model_config = {"from_attributes": True}


class AddCollaborator(BaseModel):
    telegram_user_id: int
    name: str | None = None
    username: str | None = None


class EventCreate(BaseModel):
    title: str
    date: datetime | None = None
    guests_count: int = 1
    notes: str | None = None
    telegram_user_id: int | None = None


class EventUpdate(BaseModel):
    title: str | None = None
    date: datetime | None = None
    guests_count: int | None = None
    notes: str | None = None


class EventOut(BaseModel):
    id: int
    title: str
    date: datetime | None
    guests_count: int
    notes: str | None
    telegram_user_id: int | None = None
    event_recipes: list[EventRecipeOut] = []
    collaborators: list[CollaboratorOut] = []

    model_config = {"from_attributes": True}


class AddRecipeToEvent(BaseModel):
    recipe_id: int
    servings_multiplier: float = 1.0


class UpdateRecipeMultiplier(BaseModel):
    servings_multiplier: float
