from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from app.repositories.poi_repo import get_poi_repository
from app.schemas.pool import PoolRequest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RETRIEVAL_DB_PATH = PROJECT_ROOT / "data" / "processed" / "hefei_pois.sqlite"
EXPERIENCE_CATEGORIES = {"culture", "scenic", "entertainment", "nightlife", "outdoor"}


@dataclass
class RetrievalResult:
    poi_ids: list[str]
    stats: dict[str, int] = field(default_factory=dict)


class PoiRetrievalService:
    def __init__(self, db_path: Path | None = None, repo=None) -> None:
        self.db_path = db_path or DEFAULT_RETRIEVAL_DB_PATH
        self.repo = repo or get_poi_repository()

    def retrieve(self, request: PoolRequest, limit: int = 300) -> list[str]:
        return self.retrieve_with_stats(request, limit=limit).poi_ids

    def retrieve_with_stats(self, request: PoolRequest, limit: int = 300) -> RetrievalResult:
        city = self._city(request)
        free_text = self._query_text(request)
        liked_ids = self._liked_ids(request)
        stats = {
            "liked_candidates": 0,
            "bucket_candidates": 0,
            "fts_candidates": 0,
            "supplement_candidates": 0,
            "total_candidates": 0,
        }

        if not self._index_available() or not self._city_has_index(city):
            poi_ids = self._fallback_ids(city, limit)
            stats["total_candidates"] = len(poi_ids)
            return RetrievalResult(poi_ids=poi_ids, stats=stats)

        collected: list[str] = []
        collected.extend(self._existing_ids(liked_ids))
        stats["liked_candidates"] = len(collected)

        scenarios = self._scenario_keys(request, free_text)
        bucket_ids = self._bucket_ids(city, scenarios, limit=120)
        stats["bucket_candidates"] = len(bucket_ids)
        collected.extend(bucket_ids)

        fts_ids = self._fts_ids(city, free_text, limit=120)
        stats["fts_candidates"] = len(fts_ids)
        collected.extend(fts_ids)

        remaining = max(0, limit - len(dict.fromkeys(collected)))
        supplement_ids = self._supplement_ids(city, request, free_text, limit=remaining)
        stats["supplement_candidates"] = len(supplement_ids)
        collected.extend(supplement_ids)

        poi_ids = self._dedupe(collected, limit)
        if not poi_ids:
            poi_ids = self._fallback_ids(city, limit)
        stats["total_candidates"] = len(poi_ids)
        return RetrievalResult(poi_ids=poi_ids, stats=stats)

    def evidence_for_poi(self, poi_id: str, query: str | None = None) -> str | None:
        if not self._index_available(table_name="ugc_evidence_index"):
            return None
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """
                    SELECT snippet
                    FROM ugc_evidence_index
                    WHERE poi_id = ?
                    ORDER BY rank
                    LIMIT 1
                    """,
                    (poi_id,),
                ).fetchone()
        except sqlite3.Error:
            return None
        if row is None:
            return None
        snippet = str(row["snippet"] or "").strip()
        return snippet or None

    def _index_available(self, table_name: str = "poi_feature_index") -> bool:
        if not self.db_path.exists():
            return False
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE name = ? LIMIT 1",
                    (table_name,),
                ).fetchone()
        except sqlite3.Error:
            return False
        return row is not None

    def _city_has_index(self, city: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT 1 FROM poi_feature_index WHERE city = ? LIMIT 1",
                    (city,),
                ).fetchone()
        except sqlite3.Error:
            return False
        return row is not None

    def _bucket_ids(self, city: str, scenarios: list[str], *, limit: int) -> list[str]:
        if not scenarios:
            return []
        placeholders = ",".join("?" for _ in scenarios)
        sql = f"""
            SELECT poi_id
            FROM poi_bucket_top
            WHERE city = ? AND scenario_key IN ({placeholders})
            ORDER BY rank, score DESC
            LIMIT ?
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(sql, (city, *scenarios, limit)).fetchall()
        except sqlite3.Error:
            return []
        return [str(row[0]) for row in rows]

    def _fts_ids(self, city: str, text: str, *, limit: int) -> list[str]:
        match_query = self._fts_query(text)
        if not match_query:
            return []
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT poi_retrieval_fts.poi_id
                    FROM poi_retrieval_fts
                    JOIN poi_feature_index ON poi_feature_index.poi_id = poi_retrieval_fts.poi_id
                    WHERE poi_retrieval_fts MATCH ? AND poi_feature_index.city = ?
                    LIMIT ?
                    """,
                    (match_query, city, limit),
                ).fetchall()
        except sqlite3.Error:
            return self._like_ids(city, text, limit=limit)
        return [str(row[0]) for row in rows]

    def _like_ids(self, city: str, text: str, *, limit: int) -> list[str]:
        terms = self._terms(text)[:8]
        if not terms:
            return []
        clauses = " OR ".join("search_text LIKE ?" for _ in terms)
        params = [f"%{term}%" for term in terms]
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    f"""
                    SELECT poi_retrieval_fts.poi_id
                    FROM poi_retrieval_fts
                    JOIN poi_feature_index ON poi_feature_index.poi_id = poi_retrieval_fts.poi_id
                    WHERE poi_feature_index.city = ? AND ({clauses})
                    LIMIT ?
                    """,
                    (city, *params, limit),
                ).fetchall()
        except sqlite3.Error:
            return []
        return [str(row[0]) for row in rows]

    def _supplement_ids(
        self,
        city: str,
        request: PoolRequest,
        free_text: str,
        *,
        limit: int,
    ) -> list[str]:
        if limit <= 0:
            return []
        ids: list[str] = []
        budget = self._budget(request)
        avoid_queue = self._avoid_queue(request, free_text)
        groups = [
            ("category = ?", ("restaurant",), 80),
            ("category IN ('scenic', 'culture', 'entertainment', 'nightlife', 'outdoor')", (), 80),
            ("category = ?", ("cafe",), 40),
            ("category = ?", ("shopping",), 50),
        ]
        for predicate, extra_params, group_limit in groups:
            if len(ids) >= limit:
                break
            where_parts = ["city = ?", predicate]
            params: list[object] = [city, *extra_params]
            if budget is not None:
                where_parts.append("(price_band IN ('free', 'low', 'mid') OR ? >= 150)")
                params.append(budget)
            if avoid_queue:
                where_parts.append("is_low_queue = 1")
            sql = f"""
                SELECT poi_id
                FROM poi_feature_index
                WHERE {' AND '.join(where_parts)}
                ORDER BY static_score DESC
                LIMIT ?
            """
            params.append(min(group_limit, limit - len(ids)))
            try:
                with sqlite3.connect(self.db_path) as conn:
                    rows = conn.execute(sql, params).fetchall()
            except sqlite3.Error:
                continue
            ids.extend(str(row[0]) for row in rows)
        if len(ids) < limit:
            ids.extend(self._top_static_ids(city, limit=limit - len(ids)))
        return self._dedupe(ids, limit)

    def _top_static_ids(self, city: str, *, limit: int) -> list[str]:
        if limit <= 0:
            return []
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT poi_id
                    FROM poi_feature_index
                    WHERE city = ?
                    ORDER BY static_score DESC
                    LIMIT ?
                    """,
                    (city, limit),
                ).fetchall()
        except sqlite3.Error:
            return []
        return [str(row[0]) for row in rows]

    def _fallback_ids(self, city: str, limit: int) -> list[str]:
        candidates = self.repo.list_by_city(city)
        if not candidates and city != "hefei":
            candidates = self.repo.list_by_city("hefei")
        candidates = sorted(
            candidates,
            key=lambda poi: (poi.category != "restaurant", -poi.rating, poi.queue_estimate.get("weekend_peak", 99)),
        )
        return [poi.id for poi in candidates[:limit]]

    def _existing_ids(self, poi_ids: Iterable[str]) -> list[str]:
        existing = {poi.id for poi in self.repo.get_many(poi_ids)}
        return [poi_id for poi_id in poi_ids if poi_id in existing]

    def _liked_ids(self, request: PoolRequest) -> list[str]:
        if not request.preference_snapshot:
            return []
        return list(request.preference_snapshot.liked_poi_ids)

    def _city(self, request: PoolRequest) -> str:
        if request.need_profile:
            return request.need_profile.destination.city or request.city
        return request.city

    def _budget(self, request: PoolRequest) -> int | None:
        if request.need_profile and request.need_profile.budget.budget_per_person is not None:
            return request.need_profile.budget.budget_per_person
        return request.budget_per_person

    def _query_text(self, request: PoolRequest) -> str:
        parts: list[object] = [
            request.free_text,
            *request.persona_tags,
        ]
        if request.need_profile:
            profile = request.need_profile
            parts.extend(
                [
                    profile.raw_query,
                    profile.party_type,
                    profile.destination.target_area,
                    profile.route_style,
                    profile.activity_preferences,
                    profile.food_preferences,
                    profile.taste_preferences,
                    profile.avoid,
                    profile.must_visit,
                ]
            )
        if request.preference_snapshot:
            parts.extend(
                [
                    request.preference_snapshot.tag_weights.keys(),
                    request.preference_snapshot.keyword_weights.keys(),
                    request.preference_snapshot.category_weights.keys(),
                ]
            )
        return " ".join(str(item) for item in _flatten(parts) if item)

    def _scenario_keys(self, request: PoolRequest, free_text: str) -> list[str]:
        text = free_text.lower()
        scenarios = ["local_food"]
        if self._avoid_queue(request, free_text):
            scenarios.append("low_queue_food")
        if any(token in text for token in ["photo", "photogenic", "拍照", "出片", "打卡", "风景", "散步"]):
            scenarios.extend(["photo_walk", "couple_photo_food"])
        if any(token in text for token in ["shopping", "mall", "shop", "商场", "购物", "逛街"]):
            scenarios.append("shopping")
        if any(token in text for token in ["scenic", "park", "walk", "景点", "公园", "文化", "展览", "散步"]):
            scenarios.append("scenic")
        budget = self._budget(request)
        if budget is not None and budget <= 80:
            scenarios.append("low_budget")
        return list(dict.fromkeys(scenarios))

    def _avoid_queue(self, request: PoolRequest, free_text: str) -> bool:
        text = free_text.lower()
        if any(token in text for token in ["少排队", "不排队", "排队少", "避开排队", "low queue", "no queue"]):
            return True
        return bool(request.need_profile and any("排队" in item for item in request.need_profile.avoid))

    def _fts_query(self, text: str) -> str:
        terms = self._terms(text)
        if not terms:
            return ""
        return " OR ".join(f'"{term}"' for term in terms[:16])

    def _terms(self, text: str) -> list[str]:
        raw_terms = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", text.lower())
        terms: list[str] = []
        for term in raw_terms:
            if len(term) <= 1:
                continue
            terms.append(term)
            if re.fullmatch(r"[\u4e00-\u9fff]+", term) and len(term) > 2:
                terms.extend(term[index : index + 2] for index in range(len(term) - 1))
        return list(dict.fromkeys(terms))

    def _dedupe(self, poi_ids: Iterable[str], limit: int) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for poi_id in poi_ids:
            if poi_id in seen:
                continue
            seen.add(poi_id)
            deduped.append(poi_id)
            if len(deduped) >= limit:
                break
        return deduped


def _flatten(values: Iterable[object]) -> Iterable[object]:
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            yield from _flatten(value)
        elif hasattr(value, "__iter__") and not isinstance(value, (str, bytes, dict)):
            yield from value
        else:
            yield value
