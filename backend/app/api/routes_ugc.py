from fastapi import APIRouter

from app.schemas.ugc import UgcFeedItem
from app.services.ugc_feed_service import UgcFeedService

router = APIRouter(prefix="/ugc", tags=["ugc"])


@router.get("/feed", response_model=list[UgcFeedItem])
def list_ugc_feed(city: str = "hefei", limit: int = 24) -> list[UgcFeedItem]:
    return UgcFeedService().list_feed(city=city, limit=limit)
