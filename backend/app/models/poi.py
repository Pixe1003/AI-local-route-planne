from sqlalchemy import JSON, DECIMAL, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Poi(Base):
    __tablename__ = "pois"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sub_category: Mapped[str | None] = mapped_column(String(64))
    address: Mapped[str | None] = mapped_column(String(512))
    latitude: Mapped[float] = mapped_column(DECIMAL(10, 7), nullable=False)
    longitude: Mapped[float] = mapped_column(DECIMAL(10, 7), nullable=False)
    rating: Mapped[float | None] = mapped_column(DECIMAL(3, 2), index=True)
    price_per_person: Mapped[int | None] = mapped_column(Integer)
    open_hours: Mapped[dict | None] = mapped_column(JSON)
    tags: Mapped[list | None] = mapped_column(JSON)
    cover_image: Mapped[str | None] = mapped_column(String(512))
    review_count: Mapped[int] = mapped_column(Integer, default=0)
