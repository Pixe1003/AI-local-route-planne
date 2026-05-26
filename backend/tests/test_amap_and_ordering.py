"""Tests for the Amap transport integration and travel-time-aware ordering.

These cover the new behaviour added alongside the unified-refactor fixes:
- estimate_transport prefers Amap when available and falls back to haversine,
- the Amap client degrades gracefully (no key / transit without a city),
- optimize_visit_order keeps the style anchor first and returns every stop.
"""

from app.repositories.seed_data import OPEN_HOURS
from app.schemas.poi import HighlightQuote, PoiDetail


def _poi(poi_id: str, lat: float, lng: float, category: str = "scenic") -> PoiDetail:
    return PoiDetail(
        id=poi_id,
        name=f"{poi_id} name",
        city="hefei",
        category=category,
        sub_category=category,
        address="合肥市测试地址",
        latitude=lat,
        longitude=lng,
        rating=4.6,
        price_per_person=50,
        open_hours=OPEN_HOURS,
        tags=[category],
        cover_image=None,
        review_count=100,
        queue_estimate={"weekday_peak": 8, "weekend_peak": 12},
        visit_duration=50,
        best_time_slots=["weekend_afternoon"],
        avoid_time_slots=[],
        highlight_quotes=[HighlightQuote(quote="适合散步拍照。", source="ugc")],
        high_freq_keywords=[{"keyword": category, "count": 80}],
        hidden_menu=[],
        avoid_tips=[],
        suitable_for=["friends"],
        atmosphere=["relaxed"],
    )


def test_estimate_transport_falls_back_to_haversine_when_amap_unavailable(monkeypatch):
    from app.solver import distance as distance_module

    monkeypatch.setattr(distance_module.amap_client, "estimate_leg", lambda *args, **kwargs: None)
    a = _poi("a", 31.82, 117.29)
    b = _poi("b", 31.83, 117.30)

    transport = distance_module.estimate_transport(a, b)

    assert transport.distance_meters == distance_module.haversine_meters(a, b)
    assert transport.mode in {"walking", "transit", "driving"}


def test_estimate_transport_prefers_amap_when_available(monkeypatch):
    from app.solver import distance as distance_module

    monkeypatch.setattr(
        distance_module.amap_client,
        "estimate_leg",
        lambda mode, origin, destination, city=None: (12, 3456),
    )
    a = _poi("a", 31.82, 117.29)
    b = _poi("b", 31.99, 117.55)

    transport = distance_module.estimate_transport(a, b)

    assert (transport.duration_min, transport.distance_meters) == (12, 3456)


def test_amap_client_is_disabled_without_key():
    from app.solver import amap_client

    client = amap_client.AmapDirectionClient(key="")
    assert client.enabled is False
    assert client.leg("walking", (31.82, 117.29), (31.83, 117.30)) is None


def test_amap_client_transit_requires_city():
    from app.solver import amap_client

    client = amap_client.AmapDirectionClient(key="test-key")
    # No city -> short-circuits before any network call.
    assert client.leg("transit", (31.82, 117.29), (31.99, 117.55)) is None


def test_amap_client_parses_walking_response(monkeypatch):
    from app.solver import amap_client

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "1", "route": {"paths": [{"duration": "600", "distance": "800"}]}}

    monkeypatch.setattr(amap_client.httpx, "get", lambda *args, **kwargs: FakeResponse())
    client = amap_client.AmapDirectionClient(key="test-key")

    assert client.leg("walking", (31.82, 117.29), (31.83, 117.30)) == (10, 800)


def test_amap_client_returns_none_on_error_status(monkeypatch):
    from app.solver import amap_client

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "0", "info": "INVALID_PARAMS"}

    monkeypatch.setattr(amap_client.httpx, "get", lambda *args, **kwargs: FakeResponse())
    client = amap_client.AmapDirectionClient(key="test-key")

    assert client.leg("walking", (31.82, 117.29), (31.83, 117.30)) is None


def test_optimize_visit_order_keeps_anchor_first_and_preserves_set():
    from app.solver.ordering import optimize_visit_order

    pois = [
        _poi("p0", 31.80, 117.20),
        _poi("p1", 31.90, 117.40),
        _poi("p2", 31.81, 117.21),
        _poi("p3", 31.89, 117.39),
    ]

    ordered = optimize_visit_order(pois, start_id="p2")

    assert ordered[0].id == "p2"
    assert {poi.id for poi in ordered} == {"p0", "p1", "p2", "p3"}
    assert len(ordered) == len(pois)
