import json
from pathlib import Path
from types import SimpleNamespace

from app.agent.tools import get_tool_registry
from app.repositories.ugc_vector_repo import UgcVectorRepo
from app.schemas.pool import PoolRequest, TimeWindow
from app.services.poi_scoring_service import PoiScoringService
from app.services.pool_service import PoolService
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


def test_ugc_feed_balances_food_experience_and_shopping_cards(tmp_path: Path) -> None:
    rows = []
    for index in range(18):
        rows.append(
            {
                "poi_id": f"food_{index}",
                "poi_name": f"Food {index}",
                "sub_category": "中餐厅",
                "reviews": [{"rating": 4.5, "content": f"food review {index}"}],
            }
        )
    for index in range(8):
        rows.append(
            {
                "poi_id": f"scenic_{index}",
                "poi_name": f"Scenic {index}",
                "sub_category": "旅游景点",
                "reviews": [{"rating": 4.5, "content": f"scenic review {index}"}],
            }
        )
    for index in range(6):
        rows.append(
            {
                "poi_id": f"shopping_{index}",
                "poi_name": f"Shopping {index}",
                "sub_category": "特色商业街",
                "reviews": [{"rating": 4.5, "content": f"shopping review {index}"}],
            }
        )
    data_path = tmp_path / "ugc.jsonl"
    data_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")

    cards = UgcFeedService(ugc_repo=UgcVectorRepo(data_path)).list_feed(city="hefei", limit=24)
    counts = {}
    for card in cards:
        counts[card.category] = counts.get(card.category, 0) + 1

    assert counts["restaurant"] == 16
    assert counts["scenic"] == 5
    assert counts["shopping"] == 3


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


def test_pool_balanced_selection_keeps_food_primary_and_surfaces_other_categories() -> None:
    service = PoolService.__new__(PoolService)
    scored = []
    for index in range(20):
        scored.append((1 - index * 0.001, SimpleNamespace(id=f"food_{index}", category="restaurant")))
    for index in range(10):
        scored.append((0.8 - index * 0.001, SimpleNamespace(id=f"scenic_{index}", category="scenic")))
    for index in range(5):
        scored.append((0.7 - index * 0.001, SimpleNamespace(id=f"shopping_{index}", category="shopping")))

    selected = service._select_balanced_pool(
        scored,
        request=PoolRequest(
            user_id="mock_user",
            city="hefei",
            date="2026-05-15",
            time_window=TimeWindow(start="13:00", end="21:00"),
            free_text="想吃饭，也想顺路拍照和逛街",
        ),
        limit=24,
    )
    counts = {}
    for _, poi in selected:
        counts[poi.category] = counts.get(poi.category, 0) + 1

    assert counts["restaurant"] == 12
    assert counts["scenic"] == 8
    assert counts["shopping"] == 4
