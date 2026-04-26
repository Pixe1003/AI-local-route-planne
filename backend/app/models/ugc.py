from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PoiEnriched(Base):
    __tablename__ = "poi_enriched"

    poi_id: Mapped[str] = mapped_column(String(64), ForeignKey("pois.id"), primary_key=True)
    queue_estimate: Mapped[dict | None] = mapped_column(JSON)
    visit_duration: Mapped[int | None] = mapped_column(Integer)
    best_time_slots: Mapped[list | None] = mapped_column(JSON)
    avoid_time_slots: Mapped[list | None] = mapped_column(JSON)
    highlight_quotes: Mapped[list | None] = mapped_column(JSON)
    high_freq_keywords: Mapped[list | None] = mapped_column(JSON)
    hidden_menu: Mapped[list | None] = mapped_column(JSON)
    avoid_tips: Mapped[list | None] = mapped_column(JSON)
    suitable_for: Mapped[list | None] = mapped_column(JSON)
    atmosphere: Mapped[list | None] = mapped_column(JSON)


class UgcReview(Base):
    __tablename__ = "ugc_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    poi_id: Mapped[str] = mapped_column(String(64), ForeignKey("pois.id"), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str | None] = mapped_column(String(32))
    embedding_id: Mapped[str | None] = mapped_column(String(64))
