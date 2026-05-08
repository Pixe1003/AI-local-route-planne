from pydantic import BaseModel


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
