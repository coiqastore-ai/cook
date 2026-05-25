from pydantic import BaseModel


class ShoppingItemOut(BaseModel):
    id: int
    event_id: int
    ingredient_name: str
    total_grams: float | None
    total_display: str | None
    bought: bool

    model_config = {"from_attributes": True}


class ShoppingItemUpdate(BaseModel):
    bought: bool
