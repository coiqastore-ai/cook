from pydantic import BaseModel


class TimelineTaskOut(BaseModel):
    id: int
    event_id: int
    recipe_id: int | None
    offset_hours: float
    action: str
    duration_min: int | None

    model_config = {"from_attributes": True}
