from collections import Counter
from datetime import datetime, timedelta, timezone

from app.agent.session_summarizer import summarize_session
from app.agent.store import _conn, list_sessions
from app.repositories.poi_repo import get_poi_repository
from app.schemas.user_memory import UserFacts


CACHE_TTL = timedelta(minutes=5)
_CACHE: dict[str, tuple[UserFacts, datetime]] = {}


def get_user_facts(user_id: str, *, force_refresh: bool = False) -> UserFacts:
    now = datetime.now(timezone.utc)
    if not force_refresh:
        cached = _CACHE.get(user_id)
        if cached and now - cached[1] < CACHE_TTL:
            return cached[0]
        row = _read_facts_row(user_id)
        if row:
            updated_at = _parse_datetime(row[1])
            if updated_at and now - updated_at < CACHE_TTL:
                facts = UserFacts.model_validate_json(row[0])
                _CACHE[user_id] = (facts, now)
                return facts

    facts = derive_facts(user_id)
    _write_facts_row(facts)
    _CACHE[user_id] = (facts, now)
    return facts


def invalidate_facts(user_id: str) -> None:
    _CACHE.pop(user_id, None)
    with _conn() as conn:
        conn.execute("DELETE FROM user_facts WHERE user_id = ?", (user_id,))


def derive_facts(user_id: str) -> UserFacts:
    sessions = [state for state in list_sessions(user_id, limit=50) if state.memory.story_plan]
    now = datetime.now(timezone.utc)
    if not sessions:
        return UserFacts(user_id=user_id, updated_at=now)

    summaries = [summarize_session(state) for state in sessions]
    budgets = [
        state.context.budget_per_person
        for state in sessions
        if state.context.budget_per_person is not None
    ]
    party_types = [state.context.party for state in sessions if state.context.party]
    time_buckets = [_bucket_time_window(state) for state in sessions]
    category_total: Counter[str] = Counter()
    rejected_pois: list[str] = []

    for summary in summaries:
        category_total.update(summary.category_distribution)
        rejected_pois.extend(summary.rejected_poi_ids)

    rejected_pois = list(dict.fromkeys(rejected_pois))[-20:]
    return UserFacts(
        user_id=user_id,
        typical_budget_range=(min(budgets), max(budgets)) if budgets else None,
        typical_party_type=Counter(party_types).most_common(1)[0][0] if party_types else None,
        typical_time_windows=[
            bucket for bucket, _ in Counter(item for item in time_buckets if item).most_common(2)
        ],
        favorite_districts=_favorite_districts(summaries),
        favorite_categories=[category for category, _ in category_total.most_common(3)],
        avoid_categories=_infer_avoid_categories(rejected_pois),
        rejected_poi_ids=rejected_pois,
        session_count=len(sessions),
        updated_at=now,
    )


def _bucket_time_window(state) -> str | None:
    try:
        date_obj = datetime.fromisoformat(state.context.date)
        hour = int(state.context.time_window.start.split(":", 1)[0])
    except (AttributeError, ValueError):
        return None
    period = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
    prefix = "weekend" if date_obj.weekday() >= 5 else "weekday"
    return f"{prefix}_{period}"


def _favorite_districts(summaries) -> list[str]:
    repo = get_poi_repository()
    districts: Counter[str] = Counter()
    for summary in summaries:
        for poi_id in summary.stop_poi_ids:
            try:
                poi = repo.get(poi_id)
            except KeyError:
                continue
            district = _district_from_address(poi.address)
            if district:
                districts[district] += 1
    return [district for district, _ in districts.most_common(3)]


def _infer_avoid_categories(rejected_poi_ids: list[str]) -> list[str]:
    if not rejected_poi_ids:
        return []
    repo = get_poi_repository()
    categories: Counter[str] = Counter()
    for poi_id in rejected_poi_ids:
        try:
            categories[repo.get(poi_id).category] += 1
        except KeyError:
            continue
    return [category for category, count in categories.items() if count >= 2]


def _district_from_address(address: str | None) -> str | None:
    if not address:
        return None
    for token in ("蜀山区", "庐阳区", "包河区", "瑶海区", "肥西县", "合肥市"):
        if token in address:
            return token
    return address.split()[0][:12] if address.strip() else None


def _read_facts_row(user_id: str):
    with _conn() as conn:
        return conn.execute(
            "SELECT facts_json, updated_at FROM user_facts WHERE user_id = ?",
            (user_id,),
        ).fetchone()


def _write_facts_row(facts: UserFacts) -> None:
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO user_facts (user_id, facts_json, session_count, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                facts_json = excluded.facts_json,
                session_count = excluded.session_count,
                updated_at = excluded.updated_at
            """,
            (
                facts.user_id,
                facts.model_dump_json(),
                facts.session_count,
                facts.updated_at.isoformat(),
            ),
        )


def _parse_datetime(raw: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
