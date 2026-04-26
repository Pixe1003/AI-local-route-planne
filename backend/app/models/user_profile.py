from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    persona_tags: Mapped[list | None] = mapped_column(JSON)
    pace_preference: Mapped[str | None] = mapped_column(String(32))
    budget_level: Mapped[str | None] = mapped_column(String(32))
    avoid_categories: Mapped[list | None] = mapped_column(JSON)
    history_summary: Mapped[dict | None] = mapped_column(JSON)
