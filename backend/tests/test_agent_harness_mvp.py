from fastapi.testclient import TestClient

from app.main import app
from app.schemas.onboarding import OnboardingAnalyzeRequest, UserNeedProfile
from app.schemas.plan import PlanContext, PlanRequest, RouteMetrics, RouteSkeleton, TimeWindow
from app.services.onboarding_service import OnboardingService
from app.services.plan_service import PlanService
from app.services.route_replanner import ReplanEvent, RouteReplanner
from app.services.route_validator import RouteValidator
from app.services.solver_service import SolverService


def test_onboarding_identifies_missing_slots_and_profile_signals():
    response = OnboardingService().analyze(
        OnboardingAnalyzeRequest(query="下午想在上海轻松逛逛，吃点本地菜，不想排队")
    )

    assert response.can_plan is True
    assert response.should_ask_followup is True
    assert 0.5 <= response.completeness_score < 0.8
    assert "budget_per_person" in response.missing_slots
    assert "party_type" in response.missing_slots
    assert response.extracted_profile.destination.city == "shanghai"
    assert "少排队" in response.extracted_profile.route_style
    assert "本地菜" in response.extracted_profile.food_preferences


def test_onboarding_profile_endpoint_feeds_pool_and_plan_without_hardcoded_context():
    client = TestClient(app)

    profile_response = client.post(
        "/api/onboarding/profile",
        json={
            "query": "今天 14:00 到 20:00 在上海从人民广场出发，情侣想拍照吃本地菜，人均 180，少排队",
            "answers": {},
        },
    )
    assert profile_response.status_code == 200
    profile = profile_response.json()["profile"]
    assert profile["party_type"] == "couple"
    assert profile["budget"]["budget_per_person"] == 180
    assert profile["time"]["start_time"] == "14:00"
    assert profile["time"]["end_time"] == "20:00"

    pool_response = client.post(
        "/api/pool/generate",
        json={"user_id": "mock_user", "city": "shanghai", "date": "2026-05-02", "need_profile": profile},
    )
    assert pool_response.status_code == 200
    pool_payload = pool_response.json()
    assert pool_payload["default_selected_ids"]

    plan_response = client.post(
        "/api/plan/generate",
        json={
            "pool_id": pool_payload["pool_id"],
            "selected_poi_ids": pool_payload["default_selected_ids"],
            "need_profile": profile,
        },
    )
    assert plan_response.status_code == 200
    plan = plan_response.json()["plans"][0]
    assert plan["summary"]["validation"]["is_valid"] is True
    assert plan["stops"][0]["score_breakdown"]
    assert "评分依据" in plan["stops"][0]["why_this_one"]


def test_route_validator_rejects_and_solver_repairs_over_time_routes():
    context = PlanContext(
        city="shanghai",
        date="2026-05-02",
        time_window=TimeWindow(start="13:00", end="14:30"),
        party="couple",
        budget_per_person=300,
    )
    profile = UserNeedProfile.from_plan_context(context, raw_query="情侣拍照，少排队")
    intent = PlanService().intent_service.parse_intent(
        "mock_user", ["sh_poi_003", "sh_poi_010", "sh_poi_017", "sh_poi_024"], "情侣拍照，少排队", context
    )
    invalid = RouteSkeleton(
        style="relaxed",
        stops=SolverService().solve(
            intent,
            ["sh_poi_003", "sh_poi_010", "sh_poi_017", "sh_poi_024"],
            context=context,
            profile=profile,
        )[0].stops,
        dropped_poi_ids=[],
        drop_reasons={},
        metrics=RouteMetrics(
            total_duration_min=260,
            total_cost=120,
            poi_count=4,
            walking_distance_meters=0,
            queue_total_min=80,
        ),
    )

    validation = RouteValidator().validate(invalid, intent, context, profile)

    assert validation.is_valid is False
    assert any(issue.code == "time_budget_exceeded" for issue in validation.issues)

    repaired = SolverService().solve(
        intent,
        ["sh_poi_003", "sh_poi_010", "sh_poi_017", "sh_poi_024"],
        context=context,
        profile=profile,
    )[0]
    repaired_validation = RouteValidator().validate(repaired, intent, context, profile)
    assert repaired_validation.is_valid is True
    assert repaired.metrics.total_duration_min <= 90


def test_event_replanner_lowers_queue_cost_and_handles_weather():
    context = PlanContext(
        city="shanghai",
        date="2026-05-02",
        time_window=TimeWindow(start="13:00", end="21:00"),
        party="couple",
        budget_per_person=300,
    )
    request = PlanRequest(
        pool_id="pool_test",
        selected_poi_ids=["sh_poi_003", "sh_poi_010", "sh_poi_017", "sh_poi_024", "sh_poi_031"],
        free_text="想拍照吃饭",
        context=context,
    )
    original_plan = PlanService().generate_plans(request).plans[0]
    original_queue = original_plan.summary.total_queue_min

    queue_response = RouteReplanner().replan(
        original_plan,
        ReplanEvent(event_type="USER_REJECT_POI", message="少排队"),
    )

    assert queue_response.replan_level == "minor"
    assert queue_response.plan.summary.total_queue_min <= original_queue
    assert queue_response.plan.summary.validation.is_valid is True

    rain_response = RouteReplanner().replan(
        original_plan,
        ReplanEvent(event_type="WEATHER_CHANGED", message="下雨了，换雨天方案"),
    )
    outdoor_categories = {stop.category for stop in rain_response.plan.stops}
    assert rain_response.replan_level == "partial"
    assert "outdoor" not in outdoor_categories
    assert rain_response.plan.summary.validation.is_valid is True
