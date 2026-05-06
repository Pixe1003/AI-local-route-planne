from fastapi.testclient import TestClient

from app.main import app


def _make_plan_payload(client: TestClient) -> tuple[dict, dict, dict]:
    profile_response = client.post(
        "/api/onboarding/profile",
        json={
            "query": "今天 14:00 到 20:00 在上海从人民广场出发，情侣想拍照吃本地菜，人均 180，少排队",
            "answers": {},
        },
    )
    assert profile_response.status_code == 200
    profile = profile_response.json()["profile"]

    pool_response = client.post(
        "/api/pool/generate",
        json={
            "user_id": "mock_user",
            "city": "shanghai",
            "date": "2026-05-02",
            "need_profile": profile,
        },
    )
    assert pool_response.status_code == 200
    pool = pool_response.json()

    plan_response = client.post(
        "/api/plan/generate",
        json={
            "pool_id": pool["pool_id"],
            "selected_poi_ids": pool["default_selected_ids"],
            "need_profile": profile,
        },
    )
    assert plan_response.status_code == 200
    plans = plan_response.json()["plans"]
    assert plans

    planning_context = {
        "city": "shanghai",
        "date": profile["date"],
        "time_window": {
            "start": profile["time"]["start_time"],
            "end": profile["time"]["end_time"],
        },
        "party": profile["party_type"],
        "budget_per_person": profile["budget"]["budget_per_person"],
    }
    return profile, pool, {"plans": plans, "planning_context": planning_context}


def test_trip_api_creates_lists_reads_and_appends_route_versions():
    client = TestClient(app)
    profile, pool, plan_payload = _make_plan_payload(client)
    plans = plan_payload["plans"]

    save_response = client.post(
        "/api/trips/versions",
        json={
            "user_id": "mock_user",
            "profile": profile,
            "planning_context": plan_payload["planning_context"],
            "plans": plans,
            "active_plan_id": plans[0]["plan_id"],
            "pool_id": pool["pool_id"],
            "selected_poi_ids": pool["default_selected_ids"],
            "source": "initial_plan",
        },
    )

    assert save_response.status_code == 200
    trip = save_response.json()
    assert trip["trip_id"].startswith("trip_")
    assert trip["active_version_id"].startswith("version_")
    assert len(trip["versions"]) == 1
    assert trip["summary"]["version_count"] == 1
    assert trip["summary"]["cover_poi_names"]

    list_response = client.get("/api/trips", params={"user_id": "mock_user"})
    assert list_response.status_code == 200
    summaries = list_response.json()
    assert summaries[0]["trip_id"] == trip["trip_id"]
    assert summaries[0]["active_version_id"] == trip["active_version_id"]

    detail_response = client.get(f"/api/trips/{trip['trip_id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["versions"][0]["plans"][0]["plan_id"] == plans[0]["plan_id"]

    append_response = client.post(
        "/api/trips/versions",
        json={
            "trip_id": trip["trip_id"],
            "user_id": "mock_user",
            "profile": profile,
            "planning_context": plan_payload["planning_context"],
            "plans": plans,
            "active_plan_id": plans[1]["plan_id"],
            "pool_id": pool["pool_id"],
            "selected_poi_ids": pool["default_selected_ids"],
            "source": "chat_adjustment",
            "user_message": "少排队一点",
        },
    )

    assert append_response.status_code == 200
    updated = append_response.json()
    assert len(updated["versions"]) == 2
    assert updated["active_version_id"] != trip["active_version_id"]
    assert updated["summary"]["version_count"] == 2
    assert updated["versions"][-1]["active_plan_id"] == plans[1]["plan_id"]
    assert updated["versions"][-1]["user_message"] == "少排队一点"
