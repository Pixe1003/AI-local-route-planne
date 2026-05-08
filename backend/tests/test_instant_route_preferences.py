from fastapi.testclient import TestClient

from app.main import app
from app.repositories.poi_repo import get_poi_repository
from app.schemas.plan import PlanContext, PlanRequest
from app.schemas.pool import PoolRequest, TimeWindow
from app.schemas.preferences import PreferenceSnapshotRequest
from app.services.plan_service import PlanService
from app.services.poi_scoring_service import PoiScoringService
from app.services.pool_service import PoolService
from app.services.preference_service import PreferenceService


def test_ugc_feed_api_returns_demo_cards():
    client = TestClient(app)

    response = client.get("/api/ugc/feed?city=shanghai")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 12
    first = payload[0]
    assert {
        "post_id",
        "poi_id",
        "poi_name",
        "title",
        "source",
        "author",
        "cover_image",
        "quote",
        "tags",
        "category",
        "rating",
        "price_per_person",
        "estimated_queue_min",
        "city",
    } <= set(first)


def test_preference_snapshot_weights_liked_pois_and_tags():
    snapshot = PreferenceService().build_snapshot(
        PreferenceSnapshotRequest(
            user_id="mock_user",
            city="shanghai",
            liked_poi_ids=["sh_poi_001", "sh_poi_008", "sh_poi_022"],
        )
    )

    assert snapshot.source == "ugc_feed_mock"
    assert snapshot.liked_poi_ids == ["sh_poi_001", "sh_poi_008", "sh_poi_022"]
    assert snapshot.category_weights["restaurant"] > 0
    assert snapshot.category_weights["cafe"] > 0
    assert snapshot.category_weights["culture"] > 0
    assert snapshot.tag_weights
    assert snapshot.keyword_weights


def test_history_preference_score_boosts_similar_pois():
    repo = get_poi_repository()
    snapshot = PreferenceService().build_snapshot(
        PreferenceSnapshotRequest(
            user_id="mock_user",
            city="shanghai",
            liked_poi_ids=["sh_poi_001", "sh_poi_008", "sh_poi_022"],
        )
    )

    liked = PoiScoringService().score_poi(repo.get("sh_poi_001"), preference_snapshot=snapshot)
    unrelated = PoiScoringService().score_poi(repo.get("sh_poi_040"), preference_snapshot=snapshot)

    assert liked.history_preference > unrelated.history_preference
    assert liked.total > unrelated.total


def test_instant_plan_uses_preferences_and_returns_alternatives():
    snapshot = PreferenceService().build_snapshot(
        PreferenceSnapshotRequest(
            user_id="mock_user",
            city="shanghai",
            liked_poi_ids=["sh_poi_001", "sh_poi_008", "sh_poi_022"],
        )
    )
    pool = PoolService().generate_pool(
        PoolRequest(
            user_id="mock_user",
            city="shanghai",
            date="2026-05-02",
            time_window=TimeWindow(start="14:00", end="20:00"),
            persona_tags=["foodie", "photographer"],
            party="friends",
            budget_per_person=180,
            free_text="今天下午想少排队、吃本地菜、顺路拍照",
            preference_snapshot=snapshot,
        )
    )
    context = PlanContext(
        city="shanghai",
        date="2026-05-02",
        time_window=TimeWindow(start="14:00", end="20:00"),
        party="friends",
        budget_per_person=180,
    )

    plans = PlanService().generate_plans(
        PlanRequest(
            pool_id=pool.pool_id,
            selected_poi_ids=pool.default_selected_ids,
            free_text="今天下午想少排队、吃本地菜、顺路拍照",
            context=context,
            preference_snapshot=snapshot,
        )
    ).plans

    main_plan = plans[0]
    route_ids = {stop.poi_id for stop in main_plan.stops}
    alternative_ids = {candidate.poi_id for candidate in main_plan.alternative_pois}
    route_categories = {stop.category for stop in main_plan.stops}

    assert main_plan.summary.poi_count >= 3
    assert "restaurant" in route_categories
    assert route_categories & {"culture", "scenic", "entertainment", "nightlife"}
    assert route_ids & set(snapshot.liked_poi_ids)
    assert main_plan.alternative_pois
    assert route_ids.isdisjoint(alternative_ids)
    assert all("history_preference" in stop.score_breakdown for stop in main_plan.stops)


def test_low_budget_prompt_keeps_expensive_liked_poi_out_of_main_route():
    snapshot = PreferenceService().build_snapshot(
        PreferenceSnapshotRequest(
            user_id="mock_user",
            city="shanghai",
            liked_poi_ids=["sh_poi_007"],
        )
    )
    pool = PoolService().generate_pool(
        PoolRequest(
            user_id="mock_user",
            city="shanghai",
            date="2026-05-02",
            time_window=TimeWindow(start="14:00", end="18:30"),
            persona_tags=["foodie"],
            party="friends",
            budget_per_person=80,
            free_text="今天下午少排队，人均80以内，想吃本地菜",
            preference_snapshot=snapshot,
        )
    )

    plans = PlanService().generate_plans(
        PlanRequest(
            pool_id=pool.pool_id,
            selected_poi_ids=pool.default_selected_ids,
            free_text="今天下午少排队，人均80以内，想吃本地菜",
            context=PlanContext(
                city="shanghai",
                date="2026-05-02",
                time_window=TimeWindow(start="14:00", end="18:30"),
                party="friends",
                budget_per_person=80,
            ),
            preference_snapshot=snapshot,
        )
    ).plans

    main_route_ids = {stop.poi_id for stop in plans[0].stops}
    alternative_ids = {candidate.poi_id for candidate in plans[0].alternative_pois}

    assert "sh_poi_007" not in main_route_ids
    assert "sh_poi_007" in alternative_ids


def test_structured_replace_stop_uses_alternative_and_keeps_plan_valid():
    client = TestClient(app)
    snapshot = client.post(
        "/api/preferences/snapshot",
        json={
            "user_id": "mock_user",
            "city": "shanghai",
            "liked_poi_ids": ["sh_poi_001", "sh_poi_008", "sh_poi_022"],
        },
    ).json()
    pool = client.post(
        "/api/pool/generate",
        json={
            "user_id": "mock_user",
            "city": "shanghai",
            "date": "2026-05-02",
            "time_window": {"start": "14:00", "end": "20:00"},
            "persona_tags": ["foodie"],
            "party": "friends",
            "budget_per_person": 180,
            "free_text": "今天下午想少排队、吃本地菜、顺路拍照",
            "preference_snapshot": snapshot,
        },
    ).json()
    plan_payload = client.post(
        "/api/plan/generate",
        json={
            "pool_id": pool["pool_id"],
            "selected_poi_ids": pool["default_selected_ids"],
            "free_text": "今天下午想少排队、吃本地菜、顺路拍照",
            "context": {
                "city": "shanghai",
                "date": "2026-05-02",
                "time_window": {"start": "14:00", "end": "20:00"},
                "party": "friends",
                "budget_per_person": 180,
            },
            "preference_snapshot": snapshot,
        },
    ).json()
    plan = plan_payload["plans"][0]
    replacement = plan["alternative_pois"][0]

    response = client.post(
        "/api/chat/adjust",
        json={
            "plan_id": plan["plan_id"],
            "user_message": "换成这个备选",
            "chat_history": [],
            "action_type": "replace_stop",
            "target_stop_index": replacement["replace_stop_index"],
            "replacement_poi_id": replacement["poi_id"],
        },
    )

    assert response.status_code == 200
    updated = response.json()["updated_plan"]
    assert updated["stops"][replacement["replace_stop_index"]]["poi_id"] == replacement["poi_id"]
    assert updated["summary"]["validation"]["is_valid"] is True
