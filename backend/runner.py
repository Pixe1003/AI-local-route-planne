"""
端到端功能验证 Runner — 无需 pytest，直接 python runner.py 运行。

每个 case 打印 PASS / FAIL + 关键断言值，便于快速定位问题。
"""
import sys
import traceback

sys.path.insert(0, ".")  # 从 backend/ 目录运行时确保 app 包可找到


# ─── 工具函数 ───────────────────────────────────────────────────────────────

_results: list[tuple[str, bool, str]] = []


def run_case(name: str, fn):
    try:
        fn()
        _results.append((name, True, ""))
        print(f"  PASS  {name}")
    except AssertionError as e:
        msg = str(e)
        _results.append((name, False, msg))
        print(f"  FAIL  {name}\n        AssertionError: {msg}")
    except Exception:
        msg = traceback.format_exc().strip().splitlines()[-1]
        _results.append((name, False, msg))
        print(f"  FAIL  {name}\n        Exception: {msg}")


def section(title: str):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


# ─── Case 1: Onboarding — 意图槽位分析 ─────────────────────────────────────

def case_onboarding_slot_analysis():
    from app.schemas.onboarding import OnboardingAnalyzeRequest
    from app.services.onboarding_service import OnboardingService

    resp = OnboardingService().analyze(
        OnboardingAnalyzeRequest(query="下午想在上海轻松逛逛，吃点本地菜，不想排队")
    )
    print(f"        completeness={resp.completeness_score:.2f}  missing={resp.missing_slots}")
    assert resp.can_plan is True, f"can_plan={resp.can_plan}"
    assert 0.5 <= resp.completeness_score < 0.8, f"score={resp.completeness_score}"
    assert "budget_per_person" in resp.missing_slots
    assert "party_type" in resp.missing_slots
    assert resp.extracted_profile.destination.city == "shanghai"


# ─── Case 2: Pool — POI 候选集生成 ─────────────────────────────────────────

def case_pool_generation():
    from app.schemas.pool import PoolRequest, TimeWindow
    from app.services.pool_service import PoolService

    req = PoolRequest(
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
    resp = PoolService().generate_pool(req)
    all_pois = [poi for cat in resp.categories for poi in cat.pois]
    print(f"        pool_id={resp.pool_id}  pois={len(all_pois)}  selected={len(resp.default_selected_ids)}")
    assert resp.pool_id.startswith("pool_")
    assert len(all_pois) >= 15, f"poi count={len(all_pois)}"
    assert 3 <= len(resp.default_selected_ids) <= 6
    assert all(poi.why_recommend for poi in all_pois)
    assert all(0 <= poi.suitable_score <= 1 for poi in all_pois)


# ─── Case 3: Solver — 三风格路线骨架 ───────────────────────────────────────

def case_solver_three_styles():
    from app.schemas.plan import PlanContext
    from app.schemas.pool import PoolRequest, TimeWindow
    from app.services.intent_service import IntentService
    from app.services.pool_service import PoolService
    from app.services.solver_service import SolverService

    pool = PoolService().generate_pool(PoolRequest(
        user_id="mock_user",
        city="shanghai",
        date="2026-05-02",
        time_window=TimeWindow(start="13:00", end="21:00"),
        persona_tags=["couple", "foodie"],
        pace_style="balanced",
        party="couple",
        budget_per_person=300,
        free_text="想轻松一点",
    ))
    context = PlanContext(
        city="shanghai",
        date="2026-05-02",
        time_window=TimeWindow(start="13:00", end="21:00"),
        party="couple",
        budget_per_person=300,
    )
    intent = IntentService().parse_intent("mock_user", pool.default_selected_ids, "想轻松一点", context)
    skeletons = SolverService().solve(intent, pool.default_selected_ids)
    styles = [s.style for s in skeletons]
    print(f"        styles={styles}")
    assert styles == ["efficient", "relaxed", "foodie_first"], f"styles={styles}"
    sigs = {tuple(stop.poi_id for stop in s.stops) for s in skeletons}
    assert len(sigs) >= 2, "所有路线完全一样"
    assert all(s.metrics.poi_count >= 3 for s in skeletons)
    assert all(s.metrics.total_duration_min <= 480 for s in skeletons)


# ─── Case 4: PlanService — 完整生成 3 条精炼路线 ───────────────────────────

def case_plan_generation():
    from app.schemas.plan import PlanContext, PlanRequest
    from app.schemas.pool import TimeWindow
    from app.services.pool_service import PoolService
    from app.services.plan_service import PlanService

    pool = PoolService().generate_pool(
        __import__("app.schemas.pool", fromlist=["PoolRequest"]).PoolRequest(
            user_id="mock_user",
            city="shanghai",
            date="2026-05-02",
            time_window=TimeWindow(start="13:00", end="21:00"),
            persona_tags=["couple", "foodie"],
            pace_style="balanced",
            party="couple",
            budget_per_person=300,
            free_text="要有晚餐，也别太赶",
        )
    )
    req = PlanRequest(
        pool_id=pool.pool_id,
        selected_poi_ids=pool.default_selected_ids,
        free_text="要有晚餐，也别太赶",
        context=PlanContext(
            city="shanghai",
            date="2026-05-02",
            time_window=TimeWindow(start="13:00", end="21:00"),
            party="couple",
            budget_per_person=300,
        ),
    )
    resp = PlanService().generate_plans(req)
    print(f"        plans={len(resp.plans)}  titles={[p.title for p in resp.plans]}")
    assert len(resp.plans) == 3
    assert len({p.title for p in resp.plans}) == 3
    for plan in resp.plans:
        assert plan.summary.tradeoffs
        for stop in plan.stops:
            assert stop.ugc_evidence
            assert stop.score_breakdown


# ─── Case 5: RouteValidator — 超时路线被判为无效 ────────────────────────────

def case_validator_rejects_overtime():
    from app.schemas.onboarding import UserNeedProfile
    from app.schemas.plan import PlanContext, RouteMetrics, RouteSkeleton, TimeWindow
    from app.services.intent_service import IntentService
    from app.services.route_validator import RouteValidator
    from app.services.solver_service import SolverService

    context = PlanContext(
        city="shanghai",
        date="2026-05-02",
        time_window=TimeWindow(start="13:00", end="14:30"),
        party="couple",
        budget_per_person=300,
    )
    profile = UserNeedProfile.from_plan_context(context, raw_query="情侣拍照，少排队")
    selected = ["sh_poi_003", "sh_poi_010", "sh_poi_017", "sh_poi_024"]
    intent = IntentService().parse_intent("mock_user", selected, "情侣拍照，少排队", context)
    base_stops = SolverService().solve(intent, selected)[0].stops
    invalid = RouteSkeleton(
        style="relaxed",
        stops=base_stops,
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
    result = RouteValidator().validate(invalid, intent, context, profile)
    codes = [issue.code for issue in result.issues]
    print(f"        is_valid={result.is_valid}  issue_codes={codes}")
    assert result.is_valid is False
    assert "time_budget_exceeded" in codes


# ─── Case 6: RouteReplanner — 雨天和少排队事件 ─────────────────────────────

def case_replanner_events():
    from app.schemas.plan import PlanContext, PlanRequest
    from app.schemas.pool import TimeWindow
    from app.services.plan_service import PlanService
    from app.services.pool_service import PoolService
    from app.services.route_replanner import ReplanEvent, RouteReplanner

    pool = PoolService().generate_pool(
        __import__("app.schemas.pool", fromlist=["PoolRequest"]).PoolRequest(
            user_id="mock_user",
            city="shanghai",
            date="2026-05-02",
            time_window=TimeWindow(start="13:00", end="21:00"),
            persona_tags=["couple"],
            pace_style="balanced",
            party="couple",
            budget_per_person=300,
            free_text="想拍照吃饭",
        )
    )
    req = PlanRequest(
        pool_id=pool.pool_id,
        selected_poi_ids=pool.default_selected_ids,
        free_text="想拍照吃饭",
        context=PlanContext(
            city="shanghai",
            date="2026-05-02",
            time_window=TimeWindow(start="13:00", end="21:00"),
            party="couple",
            budget_per_person=300,
        ),
    )
    original = PlanService().generate_plans(req).plans[0]
    original_queue = original.summary.total_queue_min

    q_resp = RouteReplanner().replan(original, ReplanEvent(event_type="USER_REJECT_POI", message="少排队"))
    print(f"        queue_event: level={q_resp.replan_level}  queue_before={original_queue} -> after={q_resp.plan.summary.total_queue_min}")
    assert q_resp.replan_level == "minor"
    assert q_resp.plan.summary.total_queue_min <= original_queue
    assert q_resp.plan.summary.validation.is_valid is True

    rain_resp = RouteReplanner().replan(original, ReplanEvent(event_type="WEATHER_CHANGED", message="下雨了"))
    outdoor_cats = {stop.category for stop in rain_resp.plan.stops}
    print(f"        rain_event: level={rain_resp.replan_level}  categories={outdoor_cats}")
    assert rain_resp.replan_level == "partial"
    assert "outdoor" not in outdoor_cats
    assert rain_resp.plan.summary.validation.is_valid is True


# ─── Case 7: HTTP API 端到端 (via TestClient) ───────────────────────────────

def case_api_e2e():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    pool_r = client.post("/api/pool/generate", json={
        "user_id": "mock_user",
        "city": "shanghai",
        "date": "2026-05-02",
        "time_window": {"start": "13:00", "end": "21:00"},
        "persona_tags": ["couple", "foodie"],
        "pace_style": "balanced",
        "party": "couple",
        "budget_per_person": 300,
        "free_text": "希望适合情侣拍照，晚上吃饭",
    })
    assert pool_r.status_code == 200, f"pool status={pool_r.status_code} body={pool_r.text[:200]}"
    pool_payload = pool_r.json()
    print(f"        /pool/generate ok  pool_id={pool_payload['pool_id']}")

    plan_r = client.post("/api/plan/generate", json={
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
    })
    assert plan_r.status_code == 200, f"plan status={plan_r.status_code} body={plan_r.text[:200]}"
    plans = plan_r.json()["plans"]
    print(f"        /plan/generate ok  plans={len(plans)}")
    assert len(plans) == 3

    chat_r = client.post("/api/chat/adjust", json={
        "plan_id": plans[0]["plan_id"],
        "user_message": "把第二站换成不需要排队的",
        "chat_history": [],
    })
    assert chat_r.status_code == 200, f"chat status={chat_r.status_code} body={chat_r.text[:200]}"
    print(f"        /chat/adjust ok  intent={chat_r.json().get('intent_type')}")
    assert chat_r.json()["updated_plan"]["stops"]


# ─── Case 8: Onboarding HTTP 端点 + Pool/Plan 联通 ─────────────────────────

def case_onboarding_api_full_flow():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    ob_r = client.post("/api/onboarding/profile", json={
        "query": "今天 14:00 到 20:00 在上海从人民广场出发，情侣想拍照吃本地菜，人均 180，少排队",
        "answers": {},
    })
    assert ob_r.status_code == 200, f"onboarding status={ob_r.status_code}"
    profile = ob_r.json()["profile"]
    print(f"        onboarding ok  party={profile['party_type']}  budget={profile['budget']['budget_per_person']}")
    assert profile["party_type"] == "couple"
    assert profile["budget"]["budget_per_person"] == 180

    pool_r = client.post("/api/pool/generate", json={
        "user_id": "mock_user",
        "city": "shanghai",
        "date": "2026-05-02",
        "need_profile": profile,
    })
    assert pool_r.status_code == 200
    pool_payload = pool_r.json()
    assert pool_payload["default_selected_ids"]
    print(f"        pool from profile ok  selected={pool_payload['default_selected_ids'][:3]}")

    plan_r = client.post("/api/plan/generate", json={
        "pool_id": pool_payload["pool_id"],
        "selected_poi_ids": pool_payload["default_selected_ids"],
        "need_profile": profile,
    })
    assert plan_r.status_code == 200
    plan = plan_r.json()["plans"][0]
    assert plan["summary"]["validation"]["is_valid"] is True
    assert plan["stops"][0]["score_breakdown"]
    print(f"        plan from profile ok  valid={plan['summary']['validation']['is_valid']}")


# ─── 主入口 ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    section("1. Onboarding 槽位分析")
    run_case("onboarding_slot_analysis", case_onboarding_slot_analysis)

    section("2. Pool 候选集生成")
    run_case("pool_generation", case_pool_generation)

    section("3. Solver 三风格路线")
    run_case("solver_three_styles", case_solver_three_styles)

    section("4. PlanService 精炼路线")
    run_case("plan_generation", case_plan_generation)

    section("5. RouteValidator 超时检测")
    run_case("validator_rejects_overtime", case_validator_rejects_overtime)

    section("6. RouteReplanner 动态重规划")
    run_case("replanner_events", case_replanner_events)

    section("7. HTTP API 端到端")
    run_case("api_e2e", case_api_e2e)

    section("8. Onboarding API → Pool → Plan 联通")
    run_case("onboarding_api_full_flow", case_onboarding_api_full_flow)

    # ── 汇总 ──
    total = len(_results)
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = total - passed
    print(f"\n{'═' * 60}")
    status = "0 失败 [OK]" if failed == 0 else f"{failed} 失败 [FAIL]"
    print(f"  结果: {passed}/{total} 通过   {status}")
    print(f"{'═' * 60}")
    if failed:
        print("\n  失败明细:")
        for name, ok, msg in _results:
            if not ok:
                print(f"    - {name}: {msg}")
        sys.exit(1)
