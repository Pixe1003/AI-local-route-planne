from datetime import datetime, timezone


def _plan(plan_id: str):
    from app.schemas.plan import (
        PlanSummary,
        RefinedPlan,
        RefinedStop,
        RouteMetrics,
        ValidationResult,
    )

    stop = RefinedStop(
        poi_id="hf_poi_food",
        poi_name="庐州徽菜馆",
        arrival_time="14:00",
        departure_time="15:00",
        why_this_one="徽菜地道。",
        ugc_evidence=[],
        latitude=31.82,
        longitude=117.29,
        category="restaurant",
    )
    summary = PlanSummary(
        total_duration_min=60,
        total_cost=88,
        poi_count=1,
        style_highlights=["少排队"],
        tradeoffs=[],
        dropped_pois=[],
        total_queue_min=12,
        walking_distance_meters=0,
        validation=ValidationResult(is_valid=True),
    )
    return RefinedPlan(
        plan_id=plan_id,
        style="efficient",
        title="合肥半日路线",
        description="测试路线",
        stops=[stop],
        summary=summary,
        alternative_pois=[],
    )


def _request(plan_id: str, *, trip_id: str | None = None):
    from app.schemas.onboarding import UserNeedProfile
    from app.schemas.plan import PlanContext
    from app.schemas.pool import TimeWindow
    from app.schemas.trip import SaveRouteVersionRequest

    return SaveRouteVersionRequest(
        trip_id=trip_id,
        user_id="mock_user",
        profile=UserNeedProfile(date="2026-05-26", party_type="friends"),
        planning_context=PlanContext(
            city="hefei",
            date="2026-05-26",
            time_window=TimeWindow(start="14:00", end="20:00"),
            party="friends",
            budget_per_person=120,
        ),
        plans=[_plan(plan_id)],
        active_plan_id=plan_id,
        source="initial_plan" if trip_id is None else "chat_adjustment",
        user_message=None if trip_id is None else "少排队一点",
    )


def test_trip_store_persists_trips_across_service_instances(tmp_path):
    from app.repositories.trip_store import TripStore
    from app.services.trip_service import TripService

    db_path = tmp_path / "app_state.sqlite"
    first_service = TripService(store=TripStore(db_path))

    created = first_service.save_route_version(_request("plan_a"))

    second_service = TripService(store=TripStore(db_path))
    loaded = second_service.get_trip(created.trip_id)
    summaries = second_service.list_trips("mock_user")

    assert loaded is not None
    assert loaded.trip_id == created.trip_id
    assert loaded.versions[0].active_plan_id == "plan_a"
    assert summaries[0].trip_id == created.trip_id

    updated = second_service.save_route_version(_request("plan_b", trip_id=created.trip_id))

    third_service = TripService(store=TripStore(db_path))
    reloaded = third_service.get_trip(created.trip_id)

    assert reloaded is not None
    assert reloaded.active_version_id == updated.active_version_id
    assert [version.active_plan_id for version in reloaded.versions] == ["plan_a", "plan_b"]
    assert reloaded.versions[-1].user_message == "少排队一点"


def test_trip_store_orders_user_trips_by_updated_at(tmp_path):
    from app.repositories.trip_store import TripStore
    from app.schemas.onboarding import UserNeedProfile
    from app.schemas.plan import PlanContext
    from app.schemas.pool import TimeWindow
    from app.schemas.trip import RouteVersion, TripRecord, TripSummary

    store = TripStore(tmp_path / "app_state.sqlite")
    context = PlanContext(
        city="hefei",
        date="2026-05-26",
        time_window=TimeWindow(start="14:00", end="20:00"),
    )
    profile = UserNeedProfile()
    old = TripRecord(
        trip_id="trip_old",
        user_id="mock_user",
        profile=profile,
        planning_context=context,
        versions=[
            RouteVersion(
                version_id="version_old",
                plans=[_plan("plan_old")],
                active_plan_id="plan_old",
                source="initial_plan",
                created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            )
        ],
        active_version_id="version_old",
        summary=TripSummary(
            trip_id="trip_old",
            title="old",
            city="hefei",
            date="2026-05-01",
            active_version_id="version_old",
            version_count=1,
            updated_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        ),
    )
    new = old.model_copy(deep=True)
    new.trip_id = "trip_new"
    new.summary.trip_id = "trip_new"
    new.summary.title = "new"
    new.summary.updated_at = datetime(2026, 5, 2, tzinfo=timezone.utc)
    store.upsert(old)
    store.upsert(new)

    assert [trip.trip_id for trip in store.list_by_user("mock_user")] == ["trip_new", "trip_old"]
