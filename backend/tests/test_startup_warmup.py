from __future__ import annotations

from types import SimpleNamespace


def test_startup_warmup_loads_repositories_ranker_and_primes_ugc(monkeypatch) -> None:
    from app import main

    calls: list[object] = []
    fake_repo = object()

    class FakeUgcRepo:
        def search(self, query: str, *, city: str | None, top_k: int):
            calls.append(("ugc.search", query, city, top_k))
            return []

    class FakeRetrievalService:
        def __init__(self, repo=None):
            calls.append(("semantic.init", repo))

        def retrieve(self, query):
            calls.append(
                (
                    "semantic.retrieve",
                    query.text,
                    query.city,
                    query.top_k,
                    query.source_types,
                )
            )
            return []

    monkeypatch.setattr(main, "get_poi_repository", lambda: calls.append("poi") or fake_repo, raising=False)
    monkeypatch.setattr(main, "get_ugc_vector_repo", lambda: calls.append("ugc") or FakeUgcRepo(), raising=False)
    monkeypatch.setattr(main, "get_ranker", lambda model_path: calls.append(("ranker", model_path)), raising=False)
    monkeypatch.setattr(main, "RetrievalService", FakeRetrievalService, raising=False)

    settings = SimpleNamespace(
        startup_warmup_enabled=True,
        startup_warmup_query="warmup",
        default_city="hefei",
        ranker_enabled=True,
        ranker_model_path="data/models/ranker.txt",
    )

    main.run_startup_warmup(settings)

    assert calls == [
        "poi",
        "ugc",
        ("ranker", "data/models/ranker.txt"),
        ("ugc.search", "warmup", "hefei", 1),
        ("semantic.init", fake_repo),
        ("semantic.retrieve", "warmup", "hefei", 1, ["poi_profile", "ugc_review"]),
    ]


def test_startup_warmup_can_be_disabled(monkeypatch) -> None:
    from app import main

    calls: list[str] = []
    monkeypatch.setattr(main, "get_poi_repository", lambda: calls.append("poi"), raising=False)

    settings = SimpleNamespace(
        startup_warmup_enabled=False,
        startup_warmup_query="warmup",
        default_city="hefei",
        ranker_enabled=True,
        ranker_model_path="data/models/ranker.txt",
    )

    main.run_startup_warmup(settings)

    assert calls == []


def test_startup_warmup_logs_and_swallows_failures(monkeypatch) -> None:
    from app import main

    warnings: list[tuple[str, str]] = []

    def fail_repository():
        raise RuntimeError("boom")

    monkeypatch.setattr(main, "get_poi_repository", fail_repository, raising=False)
    monkeypatch.setattr(
        main.logger,
        "warning",
        lambda message, exc: warnings.append((message, str(exc))),
    )

    settings = SimpleNamespace(
        startup_warmup_enabled=True,
        startup_warmup_query="warmup",
        default_city="hefei",
        ranker_enabled=True,
        ranker_model_path="data/models/ranker.txt",
    )

    main.run_startup_warmup(settings)

    assert warnings == [("startup warmup failed: %s", "boom")]
