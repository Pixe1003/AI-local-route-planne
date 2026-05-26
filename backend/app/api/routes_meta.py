from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.repositories.poi_repo import get_poi_repository
from app.repositories.rag_index import get_rag_status

router = APIRouter(tags=["meta"])

PERSONA_TAGS = [
    "foodie",
    "local_gourmet",
    "photographer",
    "literary",
    "parent_child",
    "couple",
    "friends",
    "solo",
]


@router.get("/meta/personas")
def personas() -> list[dict[str, str]]:
    labels = {
        "foodie": "探店达人",
        "local_gourmet": "本地老饕",
        "photographer": "打卡拍照",
        "literary": "文艺青年",
        "parent_child": "亲子家庭",
        "couple": "情侣约会",
        "friends": "朋友聚会",
        "solo": "独自出行",
    }
    return [{"value": tag, "label": labels[tag]} for tag in PERSONA_TAGS]


@router.get("/meta/cities")
def cities() -> list[dict[str, str]]:
    default_city = get_settings().default_city
    cities = [
        {"value": "hefei", "label": "合肥"},
        {"value": "shanghai", "label": "上海"},
    ]
    return sorted(cities, key=lambda item: item["value"] != default_city)


@router.get("/meta/integrations")
def integrations() -> dict[str, object]:
    settings = get_settings()
    rag = get_rag_status()
    return {
        "llm": bool(settings.llm_api_key),
        "embedding": bool(settings.embedding_api_key),
        "amap": bool(settings.amap_key),
        "rag_collection_count": int(rag.get("collection_count", 0)),
    }


@router.get("/poi/{poi_id}")
def poi_detail(poi_id: str):
    repo = get_poi_repository()
    try:
        return repo.get(poi_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="POI not found") from exc
