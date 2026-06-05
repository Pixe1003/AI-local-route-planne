import time
from types import SimpleNamespace

from app.agent.tools import _compact_route_ids, _ensure_selected_route_mix
from app.schemas.poi import HighlightQuote, PoiDetail
from app.schemas.plan import HardConstraints, SoftPreferences, StructuredIntent
from app.schemas.pool import PoolRequest
from app.schemas.rag import EvidenceSnippet, RetrievedPoi
from app.services.poi_retrieval_service import RetrievalResult
from app.services.pool_service import PoolService, SemanticRetrievalGuard


def _poi(poi_id: str, category: str, *, price: int = 50) -> PoiDetail:
    return PoiDetail(
        id=poi_id,
        name=f"{poi_id} name",
        city="hefei",
        category=category,
        sub_category=category,
        address="hefei test address",
        latitude=31.82,
        longitude=117.29,
        rating=4.6,
        price_per_person=price,
        open_hours={},
        tags=[category, "low_queue"],
        cover_image=None,
        review_count=200,
        queue_estimate={"weekday_peak": 8, "weekend_peak": 12},
        visit_duration=45,
        best_time_slots=[],
        avoid_time_slots=[],
        highlight_quotes=[HighlightQuote(quote="demo local evidence", source="demo", category="ugc_review")],
        high_freq_keywords=[{"keyword": category, "count": 20}],
        hidden_menu=[],
        avoid_tips=[],
        suitable_for=["friends"],
        atmosphere=["relaxed"],
    )


class PoolRepo:
    def __init__(self, pois: list[PoiDetail]) -> None:
        self._pois = {poi.id: poi for poi in pois}

    def get(self, poi_id: str) -> PoiDetail:
        return self._pois[poi_id]

    def get_many(self, poi_ids):
        return [self._pois[poi_id] for poi_id in poi_ids if poi_id in self._pois]

    def list_by_city(self, city: str, limit: int | None = None):
        pois = [poi for poi in self._pois.values() if poi.city == city]
        return pois[:limit] if limit else pois


class FakeStructuredRetrieval:
    def __init__(self, poi_ids: list[str]) -> None:
        self.poi_ids = poi_ids

    def retrieve_with_stats(self, request, limit: int = 300) -> RetrievalResult:
        return RetrievalResult(
            poi_ids=self.poi_ids[:limit],
            stats={
                "total_candidates": len(self.poi_ids[:limit]),
                "bucket_candidates": len(self.poi_ids[:limit]),
                "fts_candidates": 0,
                "supplement_candidates": 0,
            },
        )

    def evidence_for_poi(self, poi_id: str, query: str | None = None) -> str | None:
        return None


class FakeSemanticRetrieval:
    def __init__(self, results: list[RetrievedPoi] | None = None, *, delay_seconds: float = 0.0) -> None:
        self.results = results or []
        self.delay_seconds = delay_seconds
        self.calls = []

    def retrieve(self, query):
        self.calls.append(query)
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        return self.results


def _semantic_result(poi_id: str, source_type: str = "ugc_review") -> RetrievedPoi:
    return RetrievedPoi(
        poi_id=poi_id,
        score=0.91,
        evidence_snippets=[
            EvidenceSnippet(
                doc_id=f"{source_type}:{poi_id}",
                source_type=source_type,
                text=f"{poi_id} semantic evidence",
                score=0.91,
            )
        ],
        provenance=[f"semantic_{source_type}"],
    )


def _repo_with_budget_pool() -> PoolRepo:
    pois = [
        *[_poi(f"food_{index}", "restaurant", price=45) for index in range(18)],
        *[_poi(f"culture_{index}", "culture", price=20) for index in range(8)],
        *[_poi(f"cafe_{index}", "cafe", price=35) for index in range(6)],
        _poi("semantic_food", "restaurant", price=50),
        _poi("semantic_culture", "culture", price=30),
    ]
    return PoolRepo(pois)


def _settings(**overrides):
    values = {
        "rag_enabled": True,
        "semantic_retrieval_timeout_ms": 1200,
        "budget_first_semantic_timeout_ms": 600,
        "budget_first_threshold": 100,
        "semantic_timeout_cooldown_seconds": 60,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_budget_first_skips_semantic_retrieval_when_structured_pool_is_sufficient(monkeypatch):
    monkeypatch.setattr("app.services.pool_service.get_settings", lambda: _settings())
    SemanticRetrievalGuard.reset_cooldown()
    repo = _repo_with_budget_pool()
    structured_ids = [poi.id for poi in repo.list_by_city("hefei") if not poi.id.startswith("semantic_")][:30]
    semantic = FakeSemanticRetrieval(results=[_semantic_result("semantic_food")])

    pool = PoolService(
        repo=repo,
        retrieval_service=FakeStructuredRetrieval(structured_ids),
        semantic_retrieval=semantic,
    ).generate_pool(
        PoolRequest(
            user_id="u1",
            city="hefei",
            budget_per_person=80,
            free_text="budget friendly local food with no expensive stops",
        )
    )

    assert semantic.calls == []
    assert pool.meta.total_count >= 24
    service_stats = pool.model_config  # keep pydantic model evaluated before checking service below
    assert service_stats is not None


def test_budget_first_service_records_skip_diagnostics(monkeypatch):
    monkeypatch.setattr("app.services.pool_service.get_settings", lambda: _settings())
    SemanticRetrievalGuard.reset_cooldown()
    repo = _repo_with_budget_pool()
    structured_ids = [poi.id for poi in repo.list_by_city("hefei") if not poi.id.startswith("semantic_")][:30]
    semantic = FakeSemanticRetrieval(results=[_semantic_result("semantic_food")])
    service = PoolService(
        repo=repo,
        retrieval_service=FakeStructuredRetrieval(structured_ids),
        semantic_retrieval=semantic,
    )

    service.generate_pool(
        PoolRequest(
            user_id="u1",
            city="hefei",
            budget_per_person=80,
            free_text="budget friendly local food with no expensive stops",
        )
    )

    assert service.last_retrieval_stats["retrieval_mode"] == "budget_first"
    assert service.last_retrieval_stats["semantic_status"] == "skipped_budget_first"
    assert service.last_retrieval_stats["semantic_query_count"] == 0
    assert service.last_retrieval_stats["structured_candidates"] >= 24


def test_budget_first_calls_semantic_once_when_structured_pool_is_insufficient(monkeypatch):
    monkeypatch.setattr("app.services.pool_service.get_settings", lambda: _settings())
    SemanticRetrievalGuard.reset_cooldown()
    repo = _repo_with_budget_pool()
    semantic = FakeSemanticRetrieval(results=[_semantic_result("semantic_food"), _semantic_result("semantic_culture")])
    service = PoolService(
        repo=repo,
        retrieval_service=FakeStructuredRetrieval(["food_0", "food_1"]),
        semantic_retrieval=semantic,
    )

    service.generate_pool(
        PoolRequest(
            user_id="u1",
            city="hefei",
            budget_per_person=80,
            free_text="budget friendly local food with no expensive stops",
        )
    )

    assert len(semantic.calls) == 1
    assert semantic.calls[0].source_types == ["poi_profile", "ugc_review"]
    assert service.last_retrieval_stats["retrieval_mode"] == "budget_first"
    assert service.last_retrieval_stats["semantic_status"] == "ok"
    assert service.last_retrieval_stats["semantic_query_count"] == 1


def test_regular_pool_semantic_retrieval_uses_one_combined_faiss_query(monkeypatch):
    monkeypatch.setattr("app.services.pool_service.get_settings", lambda: _settings())
    SemanticRetrievalGuard.reset_cooldown()
    repo = _repo_with_budget_pool()
    semantic = FakeSemanticRetrieval(results=[_semantic_result("semantic_food")])
    service = PoolService(
        repo=repo,
        retrieval_service=FakeStructuredRetrieval(["food_0", "culture_0", "cafe_0"]),
        semantic_retrieval=semantic,
    )

    service.generate_pool(PoolRequest(user_id="u1", city="hefei", budget_per_person=180, free_text="quiet food route"))

    assert len(semantic.calls) == 1
    assert semantic.calls[0].source_types == ["poi_profile", "ugc_review"]
    assert semantic.calls[0].top_k == 120
    assert service.last_retrieval_stats["retrieval_mode"] == "semantic_first"
    assert service.last_retrieval_stats["semantic_query_count"] == 1


def test_semantic_timeout_returns_structured_pool_and_enters_cooldown(monkeypatch):
    monkeypatch.setattr(
        "app.services.pool_service.get_settings",
        lambda: _settings(semantic_retrieval_timeout_ms=10, semantic_timeout_cooldown_seconds=30),
    )
    SemanticRetrievalGuard.reset_cooldown()
    repo = _repo_with_budget_pool()
    semantic = FakeSemanticRetrieval(delay_seconds=0.05)
    service = PoolService(
        repo=repo,
        retrieval_service=FakeStructuredRetrieval(["food_0", "culture_0", "cafe_0"]),
        semantic_retrieval=semantic,
    )

    pool = service.generate_pool(PoolRequest(user_id="u1", city="hefei", budget_per_person=180, free_text="quiet food"))

    assert pool.meta.total_count >= 3
    assert service.last_retrieval_stats["semantic_status"] == "timeout"
    assert service.last_retrieval_stats["semantic_query_count"] == 1

    semantic.calls.clear()
    service.generate_pool(PoolRequest(user_id="u1", city="hefei", budget_per_person=180, free_text="quiet food again"))

    assert semantic.calls == []
    assert service.last_retrieval_stats["semantic_status"] == "cooldown"
    assert service.last_retrieval_stats["semantic_query_count"] == 0
    SemanticRetrievalGuard.reset_cooldown()


def test_route_mix_guard_keeps_required_experience_when_solver_fallback_is_all_food():
    pool_pois = [
        SimpleNamespace(id="food_1", category="restaurant", suitable_score=0.9, price_per_person=30),
        SimpleNamespace(id="food_2", category="restaurant", suitable_score=0.8, price_per_person=20),
        SimpleNamespace(id="food_3", category="restaurant", suitable_score=0.7, price_per_person=20),
        SimpleNamespace(id="culture_1", category="culture", suitable_score=0.6, price_per_person=None),
    ]
    intent = StructuredIntent(
        hard_constraints=HardConstraints(
            start_time="10:00",
            end_time="15:00",
            must_include_meal=False,
            must_include_experience=True,
        ),
        soft_preferences=SoftPreferences(),
        must_visit_pois=[],
    )

    selected = _ensure_selected_route_mix(["food_1", "food_2", "food_3"], pool_pois, intent)

    assert "culture_1" in selected
    assert len(selected) == 3


def test_route_mix_guard_adds_cafe_variety_for_budget_first_routes():
    pool_pois = [
        SimpleNamespace(id="food_1", category="restaurant", suitable_score=0.9, price_per_person=30),
        SimpleNamespace(id="food_2", category="restaurant", suitable_score=0.8, price_per_person=20),
        SimpleNamespace(id="scenic_1", category="scenic", suitable_score=0.7, price_per_person=0),
        SimpleNamespace(id="cafe_1", category="cafe", suitable_score=0.65, price_per_person=15),
    ]
    intent = StructuredIntent(
        hard_constraints=HardConstraints(
            start_time="10:00",
            end_time="15:00",
            budget_total=80,
            must_include_meal=True,
            must_include_experience=False,
        ),
        soft_preferences=SoftPreferences(custom_notes=["budget friendly local food with no expensive stops"]),
        must_visit_pois=[],
    )

    selected = _ensure_selected_route_mix(["food_1", "food_2", "scenic_1"], pool_pois, intent)

    assert "cafe_1" in selected
    assert len(selected) == 3


def test_route_mix_guard_adds_cafe_for_photo_food_routes_without_budget_pressure():
    pool_pois = [
        SimpleNamespace(id="scenic_1", category="scenic", suitable_score=0.9, price_per_person=0),
        SimpleNamespace(id="food_1", category="restaurant", suitable_score=0.8, price_per_person=50),
        SimpleNamespace(id="scenic_2", category="scenic", suitable_score=0.7, price_per_person=0),
        SimpleNamespace(id="cafe_1", category="cafe", suitable_score=0.65, price_per_person=25),
    ]
    intent = StructuredIntent(
        hard_constraints=HardConstraints(
            start_time="10:00",
            end_time="15:00",
            must_include_meal=True,
            must_include_experience=True,
        ),
        soft_preferences=SoftPreferences(custom_notes=["想拍照，也想吃点本地美食"]),
        must_visit_pois=[],
    )

    selected = _ensure_selected_route_mix(["scenic_1", "food_1", "scenic_2"], pool_pois, intent)

    assert "cafe_1" in selected
    assert len(selected) == 3


def test_route_mix_guard_uses_other_new_category_when_cafe_is_unavailable():
    pool_pois = [
        SimpleNamespace(id="food_1", category="restaurant", suitable_score=0.9, price_per_person=30),
        SimpleNamespace(id="food_2", category="restaurant", suitable_score=0.8, price_per_person=20),
        SimpleNamespace(id="culture_1", category="culture", suitable_score=0.7, price_per_person=0),
        SimpleNamespace(id="shopping_1", category="shopping", suitable_score=0.65, price_per_person=25),
    ]
    intent = StructuredIntent(
        hard_constraints=HardConstraints(
            start_time="09:30",
            end_time="16:30",
            budget_total=160,
            must_include_meal=True,
            must_include_experience=True,
        ),
        soft_preferences=SoftPreferences(custom_notes=["must visit museum, then add food and culture"]),
        must_visit_pois=[],
    )

    selected = _ensure_selected_route_mix(["food_1", "culture_1", "food_2"], pool_pois, intent)

    assert "shopping_1" in selected
    assert len(selected) == 3


def test_route_mix_guard_caps_restaurants_and_interleaves_non_food_stops():
    pool_pois = [
        SimpleNamespace(
            id="food_1",
            category="restaurant",
            sub_category="hotpot",
            suitable_score=0.95,
            price_per_person=60,
        ),
        SimpleNamespace(
            id="food_2",
            category="restaurant",
            sub_category="hotpot",
            suitable_score=0.9,
            price_per_person=55,
        ),
        SimpleNamespace(
            id="food_3",
            category="restaurant",
            sub_category="snack",
            suitable_score=0.85,
            price_per_person=25,
        ),
        SimpleNamespace(
            id="food_4",
            category="restaurant",
            sub_category="western",
            suitable_score=0.8,
            price_per_person=45,
        ),
        SimpleNamespace(id="scenic_1", category="scenic", sub_category="park", suitable_score=0.88, price_per_person=0),
        SimpleNamespace(id="culture_1", category="culture", sub_category="museum", suitable_score=0.82, price_per_person=0),
    ]
    intent = StructuredIntent(
        hard_constraints=HardConstraints(
            start_time="10:00",
            end_time="15:00",
            must_include_meal=True,
            must_include_experience=True,
        ),
        soft_preferences=SoftPreferences(custom_notes=["food, museum and photo stops"]),
        must_visit_pois=[],
    )

    selected = _ensure_selected_route_mix(
        ["food_1", "food_2", "food_3", "food_4"],
        pool_pois,
        intent,
    )
    by_id = {poi.id: poi for poi in pool_pois}
    categories = [by_id[poi_id].category for poi_id in selected]
    restaurant_ids = [poi_id for poi_id in selected if by_id[poi_id].category == "restaurant"]
    restaurant_sub_categories = [by_id[poi_id].sub_category for poi_id in restaurant_ids]

    assert len(restaurant_ids) <= 2
    assert not any(left == right == "restaurant" for left, right in zip(categories, categories[1:]))
    assert len(set(restaurant_sub_categories)) == len(restaurant_sub_categories)


def test_route_mix_guard_uses_repo_sub_category_when_pool_item_lacks_it():
    pool_pois = [
        SimpleNamespace(id="hf_poi_053733", category="restaurant", suitable_score=0.606, price_per_person=20),
        SimpleNamespace(id="hf_poi_056335", category="restaurant", suitable_score=0.606, price_per_person=20),
        SimpleNamespace(id="hf_poi_005290", category="restaurant", suitable_score=0.603, price_per_person=17),
        SimpleNamespace(id="hf_scenic_poi_000160", category="scenic", suitable_score=0.61, price_per_person=10),
        SimpleNamespace(id="hf_poi_008427", category="shopping", suitable_score=0.59, price_per_person=23),
    ]
    intent = StructuredIntent(
        hard_constraints=HardConstraints(
            start_time="10:00",
            end_time="15:00",
            must_include_meal=True,
            must_include_experience=True,
        ),
        soft_preferences=SoftPreferences(custom_notes=["low queue local food and nearby stops"]),
        must_visit_pois=[],
    )

    selected = _ensure_selected_route_mix(
        ["hf_poi_053733", "hf_scenic_poi_000160", "hf_poi_008427", "hf_poi_056335"],
        pool_pois,
        intent,
    )

    assert "hf_poi_005290" in selected
    assert "hf_poi_056335" not in selected


def test_route_compaction_preserves_required_experience_category():
    class Repo:
        def __init__(self):
            self.pois = {
                "food_1": SimpleNamespace(
                    id="food_1", category="restaurant", latitude=31.0, longitude=117.0
                ),
                "culture_1": SimpleNamespace(
                    id="culture_1", category="culture", latitude=32.0, longitude=118.0
                ),
                "food_2": SimpleNamespace(
                    id="food_2", category="restaurant", latitude=31.001, longitude=117.001
                ),
                "food_3": SimpleNamespace(
                    id="food_3", category="restaurant", latitude=31.002, longitude=117.002
                ),
                "food_4": SimpleNamespace(
                    id="food_4", category="restaurant", latitude=31.003, longitude=117.003
                ),
            }

        def get_many(self, ids):
            return [self.pois[poi_id] for poi_id in ids if poi_id in self.pois]

    selected = _compact_route_ids(
        ["food_1", "culture_1", "food_2", "food_3", "food_4"],
        Repo(),
        required_category_groups=[{"culture", "scenic", "entertainment", "nightlife"}],
    )

    assert "culture_1" in selected
    assert len([poi_id for poi_id in selected if Repo().pois[poi_id].category == "restaurant"]) <= 2
    assert len(selected) >= 3


def test_route_compaction_preserves_category_spread_from_raw_route():
    class Repo:
        def __init__(self):
            self.pois = {
                "food_1": SimpleNamespace(
                    id="food_1", category="restaurant", latitude=31.0, longitude=117.0
                ),
                "culture_1": SimpleNamespace(
                    id="culture_1", category="culture", latitude=32.0, longitude=118.0
                ),
                "food_2": SimpleNamespace(
                    id="food_2", category="restaurant", latitude=31.001, longitude=117.001
                ),
                "food_3": SimpleNamespace(
                    id="food_3", category="restaurant", latitude=31.002, longitude=117.002
                ),
                "scenic_1": SimpleNamespace(
                    id="scenic_1", category="scenic", latitude=31.003, longitude=117.003
                ),
            }

        def get_many(self, ids):
            return [self.pois[poi_id] for poi_id in ids if poi_id in self.pois]

    selected = _compact_route_ids(
        ["food_1", "culture_1", "food_2", "food_3", "scenic_1"],
        Repo(),
        required_category_groups=[{"culture", "scenic", "entertainment", "nightlife"}],
    )

    categories = {Repo().pois[poi_id].category for poi_id in selected}
    assert {"restaurant", "culture", "scenic"} <= categories
    assert len(selected) == 4


def test_route_compaction_caps_and_interleaves_restaurants():
    class Repo:
        def __init__(self):
            self.pois = {
                "food_1": SimpleNamespace(
                    id="food_1",
                    category="restaurant",
                    sub_category="hotpot",
                    latitude=31.0,
                    longitude=117.0,
                ),
                "food_2": SimpleNamespace(
                    id="food_2",
                    category="restaurant",
                    sub_category="hotpot",
                    latitude=31.001,
                    longitude=117.001,
                ),
                "food_3": SimpleNamespace(
                    id="food_3",
                    category="restaurant",
                    sub_category="snack",
                    latitude=31.002,
                    longitude=117.002,
                ),
                "scenic_1": SimpleNamespace(
                    id="scenic_1", category="scenic", sub_category="park", latitude=31.003, longitude=117.003
                ),
                "culture_1": SimpleNamespace(
                    id="culture_1", category="culture", sub_category="museum", latitude=31.004, longitude=117.004
                ),
            }

        def get_many(self, ids):
            return [self.pois[poi_id] for poi_id in ids if poi_id in self.pois]

    repo = Repo()
    selected = _compact_route_ids(
        ["food_1", "food_2", "food_3", "scenic_1", "culture_1"],
        repo,
        required_category_groups=[{"culture", "scenic", "entertainment", "nightlife"}],
    )
    categories = [repo.pois[poi_id].category for poi_id in selected]
    restaurant_ids = [poi_id for poi_id in selected if repo.pois[poi_id].category == "restaurant"]
    restaurant_sub_categories = [repo.pois[poi_id].sub_category for poi_id in restaurant_ids]

    assert len(restaurant_ids) <= 2
    assert not any(left == right == "restaurant" for left, right in zip(categories, categories[1:]))
    assert len(set(restaurant_sub_categories)) == len(restaurant_sub_categories)
