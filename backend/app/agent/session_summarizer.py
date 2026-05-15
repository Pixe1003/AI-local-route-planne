from collections import Counter
from datetime import datetime, timezone

from app.agent.state import AgentState
from app.repositories.poi_repo import get_poi_repository
from app.schemas.user_memory import SessionSummary


def summarize_session(state: AgentState) -> SessionSummary:
    story = state.memory.story_plan
    rejected = _extract_rejected_pois(state)
    stop_ids = [stop.poi_id for stop in story.stops] if story else []
    stop_names: list[str] = []
    categories: Counter[str] = Counter()
    repo = get_poi_repository()

    for poi_id in stop_ids:
        try:
            poi = repo.get(poi_id)
        except KeyError:
            stop_names.append(poi_id)
            continue
        stop_names.append(poi.name)
        categories[poi.category] += 1

    return SessionSummary(
        session_id=state.goal.session_id,
        raw_query=state.goal.raw_query,
        theme=story.theme if story else None,
        narrative=story.narrative if story else None,
        stop_poi_ids=stop_ids,
        stop_poi_names=stop_names,
        category_distribution=dict(categories),
        feedback_applied=state.memory.feedback_applied,
        rejected_poi_ids=rejected,
        created_at=datetime.now(timezone.utc),
    )


def _extract_rejected_pois(state: AgentState) -> list[str]:
    feedback = state.memory.feedback_intent or {}
    if feedback.get("event_type") != "REPLACE_POI":
        return []
    original = feedback.get("_original_poi_at_target")
    return [str(original)] if original else []
