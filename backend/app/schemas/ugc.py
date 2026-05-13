from pydantic import BaseModel, Field


class UgcFeedItem(BaseModel):
    post_id: str
    poi_id: str
    poi_name: str
    title: str
    source: str
    author: str
    cover_image: str | None
    quote: str
    tags: list[str]
    category: str
    rating: float
    price_per_person: int | None
    estimated_queue_min: int | None
    city: str


class UgcReview(BaseModel):
    post_id: str
    poi_id: str
    poi_name: str
    content: str
    rating: float | None = None
    poi_rating: float | None = None
    price_per_person: int | None = None
    category: str = "restaurant"
    sub_category: str | None = None
    district: str | None = None
    city: str = "hefei"
    source: str = "simulated_ugc"
    author: str | None = None
    tags: list[str] = Field(default_factory=list)


class UgcSearchHit(BaseModel):
    post_id: str
    poi_id: str
    poi_name: str
    snippet: str
    source: str
    score: float
    rating: float | None = None
    category: str
    tags: list[str] = Field(default_factory=list)
