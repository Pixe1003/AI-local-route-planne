from fastapi import APIRouter, HTTPException

from app.agent.tools import get_tool_registry
from app.repositories.poi_repo import get_poi_repository

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
    return [{"value": "hefei", "label": "合肥"}]


@router.get("/agent/tools")
def agent_tools() -> list[dict]:
    return get_tool_registry().schemas_for_llm()


@router.get("/poi/{poi_id}")
def poi_detail(poi_id: str):
    repo = get_poi_repository()
    try:
        return repo.get(poi_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="POI not found") from exc
