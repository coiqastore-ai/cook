from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Ingredient(Base):
    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(100))
    normalized_grams: Mapped[float | None] = mapped_column(Float)

    recipe: Mapped["Recipe"] = relationship(back_populates="ingredients")
