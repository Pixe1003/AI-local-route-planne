from datetime import datetime

from pydantic import BaseModel, Field


class SessionSummary(BaseModel):
    session_id: str
    raw_query: str
    theme: str | None = None
    narrative: str | None = None
    stop_poi_ids: list[str] = Field(default_factory=list)
    stop_poi_names: list[str] = Field(default_factory=list)
    category_distribution: dict[str, int] = Field(default_factory=dict)
    feedback_applied: bool = False
    rejected_poi_ids: list[str] = Field(default_factory=list)
    created_at: datetime


class UserFacts(BaseModel):
    user_id: str
    typical_budget_range: tuple[int, int] | None = None
    typical_party_type: str | None = None
    typical_time_windows: list[str] = Field(default_factory=list)
    favorite_districts: list[str] = Field(default_factory=list)
    favorite_categories: list[str] = Field(default_factory=list)
    avoid_categories: list[str] = Field(default_factory=list)
    rejected_poi_ids: list[str] = Field(default_factory=list)
    session_count: int = 0
    updated_at: datetime

    def to_prompt_block(self) -> str:
        parts: list[str] = []
        if self.typical_budget_range:
            lo, hi = self.typical_budget_range
            parts.append(f"typical_budget=¥{lo}-{hi}")
        if self.typical_party_type:
            parts.append(f"party={self.typical_party_type}")
        if self.typical_time_windows:
            parts.append(f"time={','.join(self.typical_time_windows[:2])}")
        if self.favorite_districts:
            parts.append(f"districts={','.join(self.favorite_districts[:3])}")
        if self.favorite_categories:
            parts.append(f"likes={','.join(self.favorite_categories[:3])}")
        if self.avoid_categories:
            parts.append(f"avoids={','.join(self.avoid_categories[:3])}")
        if self.rejected_poi_ids:
            parts.append(f"rejected={len(self.rejected_poi_ids)} POIs")
        return "; ".join(parts) if parts else "no facts yet"


class SimilarSessionHit(BaseModel):
    session_id: str
    raw_query: str
    theme: str | None = None
    similarity: float
    stop_poi_names: list[str] = Field(default_factory=list)
    days_ago: int = 0
