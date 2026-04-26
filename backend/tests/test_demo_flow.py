from fastapi.testclient import TestClient

from app.main import app
from app.schemas.chat import ChatTurn
from app.schemas.plan import PlanContext, PlanRequest
from app.schemas.pool import PoolRequest, TimeWindow
from app.services.chat_service import ChatService
from app.services.intent_service import IntentService
from app.services.plan_service import PlanService
from app.services.pool_service import PoolService
from app.services.solver_service import SolverService


def sample_pool_request() -> PoolRequest:
    return PoolRequest(
        user_id="mock_user",
        city="shanghai",
        date="2026-05-02",
        time_window=TimeWindow(start="13:00", end="21:00"),
        persona_tags=["couple", "foodie"],
        pace_style="balanced",
        party="couple",
        budget_per_person=300,
        free_text="不想排队太久，想要适合拍照和吃饭",
    )


def test_pool_service_returns_demo_ready_candidate_pool():
    response = PoolService().generate_pool(sample_pool_request())

    all_pois = [poi for category in response.categories for poi in category.pois]
    assert response.pool_id.startswith("pool_")
    assert len(all_pois) >= 15
    assert len(response.default_selected_ids) >= 3
    assert len(response.default_selected_ids) <= 5
    assert all(poi.why_recommend for poi in all_pois)
    assert all(0 <= poi.suitable_score <= 1 for poi in all_pois)


def test_solver_generates_three_visibly_different_routes():
    pool = PoolService().generate_pool(sample_pool_request())
    selected_ids = pool.default_selected_ids
    context = PlanContext(
        city="shanghai",
        date="2026-05-02",
        time_window=TimeWindow(start="13:00", end="21:00"),
        party="couple",
        budget_per_person=300,
    )
    intent = IntentService().parse_intent("mock_user", selected_ids, "想轻松一点", context)

    skeletons = SolverService().solve(intent, selected_ids)

    assert [skeleton.style for skeleton in skeletons] == [
        "efficient",
        "relaxed",
        "foodie_first",
    ]
    route_signatures = {tuple(stop.poi_id for stop in skeleton.stops) for skeleton in skeletons}
    assert len(route_signatures) >= 2
    assert all(skeleton.metrics.poi_count >= 3 for skeleton in skeletons)
    assert all(skeleton.metrics.total_duration_min <= 480 for skeleton in skeletons)


def test_plan_service_refines_routes_with_ugc_and_tradeoffs():
    pool = PoolService().generate_pool(sample_pool_request())
    context = PlanContext(
        city="shanghai",
        date="2026-05-02",
        time_window=TimeWindow(start="13:00", end="21:00"),
        party="couple",
        budget_per_person=300,
    )
    intent = IntentService().parse_intent(
        "mock_user", pool.default_selected_ids, "要有晚餐，也别太赶", context
    )
    skeletons = SolverService().solve(intent, pool.default_selected_ids)

    plans = PlanService().refine_plans(skeletons, intent, context)

    assert len(plans) == 3
    assert len({plan.title for plan in plans}) == 3
    assert all(plan.summary.tradeoffs for plan in plans)
    assert all(stop.ugc_evidence for plan in plans for stop in plan.stops)


def test_chat_service_replaces_a_stop_with_lower_queue_plan():
    pool = PoolService().generate_pool(sample_pool_request())
    context = PlanContext(
        city="shanghai",
        date="2026-05-02",
        time_window=TimeWindow(start="13:00", end="21:00"),
        party="couple",
        budget_per_person=300,
    )
    request = PlanRequest(
        pool_id=pool.pool_id,
        selected_poi_ids=pool.default_selected_ids,
        free_text="想要松弛一点",
        context=context,
    )
    plans = PlanService().generate_plans(request).plans
    original_plan = plans[0]

    response = ChatService().adjust_plan(
        plan_id=original_plan.plan_id,
        user_message="把第二站换成不需要排队的",
        chat_history=[
            ChatTurn(role="user", content="想要松弛一点", timestamp=pool.meta.generated_at)
        ],
    )

    assert response.intent_type == "replace_poi"
    assert response.updated_plan is not None
    assert response.updated_plan.plan_id == original_plan.plan_id
    assert response.assistant_message
    assert response.requires_confirmation is False


def test_api_demo_flow_returns_renderable_json():
    client = TestClient(app)

    pool_response = client.post("/api/pool/generate", json=sample_pool_request().model_dump())
    assert pool_response.status_code == 200
    pool_payload = pool_response.json()
    assert pool_payload["default_selected_ids"]

    plan_response = client.post(
        "/api/plan/generate",
        json={
            "pool_id": pool_payload["pool_id"],
            "selected_poi_ids": pool_payload["default_selected_ids"],
            "free_text": "希望适合情侣拍照，晚上吃饭",
            "context": {
                "city": "shanghai",
                "date": "2026-05-02",
                "time_window": {"start": "13:00", "end": "21:00"},
                "party": "couple",
                "budget_per_person": 300,
            },
        },
    )
    assert plan_response.status_code == 200
    plans = plan_response.json()["plans"]
    assert len(plans) == 3

    chat_response = client.post(
        "/api/chat/adjust",
        json={
            "plan_id": plans[0]["plan_id"],
            "user_message": "加一杯咖啡",
            "chat_history": [],
        },
    )
    assert chat_response.status_code == 200
    assert chat_response.json()["updated_plan"]["stops"]
