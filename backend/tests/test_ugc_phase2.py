import json
from pathlib import Path
from types import SimpleNamespace

from app.agent.tools import get_tool_registry
from app.repositories.ugc_vector_repo import UgcVectorRepo
from app.services.poi_scoring_service import PoiScoringService
from app.services.ugc_feed_service import UgcFeedService


def _write_nested_reviews(path: Path) -> None:
    rows = [
        {
            "poi_id": "hf_poi_cafe",
            "poi_name": "Quiet Cafe",
            "sub_category": "cafe",
            "district": "baohe",
            "poi_rating": 4.7,
            "price_per_person": 42,
            "reviews": [
                {"rating": 4.8, "content": "quiet coffee low queue good for work"},
                {"rating": 4.2, "content": "window seats photogenic dessert"},
            ],
        },
        {
            "poi_id": "hf_poi_hotpot",
            "poi_name": "Busy Hotpot",
            "sub_category": "hotpot",
            "district": "luyang",
            "poi_rating": 4.3,
            "price_per_person": 95,
            "reviews": [
                {"rating": 4.0, "content": "spicy dinner long queue noisy table"},
            ],
        },
    ]
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")


def test_ugc_vector_repo_loads_nested_reviews_and_ranks_relevant_hits(tmp_path: Path) -> None:
    data_path = tmp_path / "ugc.jsonl"
    _write_nested_reviews(data_path)

    repo = UgcVectorRepo(data_path)

    assert len(repo.list_reviews()) == 3
    hits = repo.search("quiet coffee low queue", city="hefei", top_k=2)

    assert hits
    assert hits[0].poi_id == "hf_poi_cafe"
    assert hits[0].score > 0
    assert hits[0].snippet.startswith("quiet coffee")


def test_ugc_feed_service_prefers_real_ugc_reviews(tmp_path: Path) -> None:
    data_path = tmp_path / "ugc.jsonl"
    _write_nested_reviews(data_path)

    service = UgcFeedService(ugc_repo=UgcVectorRepo(data_path))
    cards = service.list_feed(city="hefei", limit=2)

    assert [card.poi_id for card in cards] == ["hf_poi_cafe", "hf_poi_cafe"]
    assert cards[0].quote == "quiet coffee low queue good for work"
    assert cards[0].source == "simulated_ugc"
    assert cards[0].tags[:2] == ["cafe", "baohe"]


def test_poi_scoring_uses_ugc_evidence_when_available(tmp_path: Path) -> None:
    data_path = tmp_path / "ugc.jsonl"
    _write_nested_reviews(data_path)
    repo = UgcVectorRepo(data_path)
    poi = SimpleNamespace(
        id="hf_poi_cafe",
        rating=4.2,
        review_count=30,
        price_per_person=42,
        queue_estimate={"weekend_peak": 20},
        tags=[],
        suitable_for=[],
        atmosphere=[],
        high_freq_keywords=[],
    )

    score = PoiScoringService(ugc_repo=repo).score_poi(poi, free_text="quiet coffee low queue")

    assert score.ugc_match >= 10


def test_agent_registry_exposes_ugc_search_tool() -> None:
    names = [schema["name"] for schema in get_tool_registry().schemas_for_llm()]

    assert "search_ugc_evidence" in names
