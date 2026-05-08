from pydantic import BaseModel, Field


class PreferenceSnapshotRequest(BaseModel):
    user_id: str
    liked_poi_ids: list[str] = Field(default_factory=list)
    disliked_poi_ids: list[str] = Field(default_factory=list)
    city: str = "shanghai"


class PreferenceSnapshot(BaseModel):
    user_id: str
    liked_poi_ids: list[str] = Field(default_factory=list)
    disliked_poi_ids: list[str] = Field(default_factory=list)
    tag_weights: dict[str, float] = Field(default_factory=dict)
    category_weights: dict[str, float] = Field(default_factory=dict)
    keyword_weights: dict[str, float] = Field(default_factory=dict)
    source: str = "ugc_feed_mock"
