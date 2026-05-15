from datetime import date
from typing import Any, Optional

from pydantic import BaseModel


class HighlightQuote(BaseModel):
    quote: str
    source: str
    review_date: Optional[date] = None
    category: str = "general_praise"


class PoiDetail(BaseModel):
    id: str
    name: str
    city: str
    category: str
    sub_category: Optional[str] = None
    district: Optional[str] = None
    address: str
    latitude: float
    longitude: float
    rating: float
    price_per_person: Optional[int] = None
    open_hours: dict[str, Any]
    tags: list[str]
    cover_image: Optional[str] = None
    review_count: int = 0
    queue_estimate: dict[str, int]
    visit_duration: int
    best_time_slots: list[str]
    avoid_time_slots: list[str]
    highlight_quotes: list[HighlightQuote]
    high_freq_keywords: list[dict[str, Any]]
    hidden_menu: list[str]
    avoid_tips: list[str]
    suitable_for: list[str]
    atmosphere: list[str]
