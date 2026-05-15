from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.agent.story_models import DroppedStoryPoi, StoryPlan, StoryStop
from app.config import get_settings
from app.llm.client import LlmClient


@dataclass(frozen=True)
class CandidateEvidence:
    poi_id: str
    poi_name: str
    category: str
    score: float
    price_per_person: int | None
    quote_ref: str
    quote: str


class StoryAgent:
    ROLES = ["opener", "midway", "main", "rest", "closer"]

    def __init__(self, llm: LlmClient | None = None) -> None:
        self.llm = llm or LlmClient()

    def compose(self, state: Any) -> StoryPlan:
        candidates = self._candidate_evidence(state)
        fallback = self._fallback_plan(candidates, state)
        if not candidates:
            return fallback
        settings = get_settings()
        if not settings.agent_tool_calling_enabled or not settings.llm_api_key:
            return fallback

        raw = self.llm.complete_json(
            self._build_prompt(candidates, state),
            fallback=fallback.model_dump(),
            agent_name="story_planner",
            system_prompt=(
                "You are a local route story planner. Return strict JSON only. "
                "Use only the supplied POI ids and UGC quote refs."
            ),
        )
        try:
            story = StoryPlan.model_validate(raw)
        except ValidationError:
            return fallback
        return fallback if self.post_check(story, state) else story

    def post_check(self, story: StoryPlan, state: Any) -> list[str]:
        candidates = self._candidate_evidence(state)
        candidate_ids = {item.poi_id for item in candidates}
        quote_refs = {item.quote_ref for item in candidates}
        issues: list[str] = []

        stop_ids = [stop.poi_id for stop in story.stops]
        if len(stop_ids) < 3 or len(stop_ids) > 5:
            issues.append("invalid_stop_count")
        if set(stop_ids) - candidate_ids:
            issues.append("hallucinated_poi")

        intent = state.memory.intent
        if intent:
            missing_must = set(intent.must_visit_pois) - set(stop_ids)
            if missing_must:
                issues.append("missing_must_visit")
            if set(intent.avoid_pois) & set(stop_ids):
                issues.append("included_avoided_poi")

        for stop in story.stops:
            if stop.ugc_quote_ref not in quote_refs:
                issues.append("hallucinated_ugc")
                break
        return list(dict.fromkeys(issues))

    def _fallback_plan(self, candidates: list[CandidateEvidence], state: Any) -> StoryPlan:
        selected = self._select_route_candidates(candidates, state)
        stops = [
            StoryStop(
                poi_id=item.poi_id,
                role=self.ROLES[min(index, len(self.ROLES) - 1)],
                why=self._why(item, index),
                ugc_quote_ref=item.quote_ref,
                ugc_quote=item.quote,
                suggested_dwell_min=50 if item.category == "restaurant" else 40,
            )
            for index, item in enumerate(selected)
        ]
        selected_ids = {item.poi_id for item in selected}
        dropped = [
            DroppedStoryPoi(poi_id=item.poi_id, reason="lower_story_fit")
            for item in candidates
            if item.poi_id not in selected_ids
        ][:8]
        return StoryPlan(
            theme=self._theme(selected, state),
            narrative=self._narrative(selected, state),
            stops=stops,
            dropped=dropped,
            fallback_used=True,
        )

    def _select_route_candidates(
        self,
        candidates: list[CandidateEvidence],
        state: Any,
    ) -> list[CandidateEvidence]:
        if not candidates:
            return []
        budget = (
            state.memory.intent.hard_constraints.budget_total
            if state.memory.intent and state.memory.intent.hard_constraints.budget_total
            else state.context.budget_per_person
        )
        if budget:
            budgeted = self._select_budgeted_candidates(candidates, budget)
            if len(budgeted) >= 3:
                return budgeted

        by_id = {item.poi_id: item for item in candidates}
        selected: list[CandidateEvidence] = []
        default_ids = state.memory.pool.default_selected_ids if state.memory.pool else []
        for poi_id in default_ids:
            item = by_id.get(poi_id)
            if item and item not in selected:
                selected.append(item)
            if len(selected) >= 5:
                return selected

        def append_best(category: str) -> None:
            if any(item.category == category for item in selected):
                return
            best = next((item for item in candidates if item.category == category), None)
            if best and best not in selected:
                selected.append(best)

        append_best("restaurant")
        if not any(item.category in {"culture", "scenic", "entertainment", "nightlife"} for item in selected):
            best_experience = next(
                (
                    item
                    for item in candidates
                    if item.category in {"culture", "scenic", "entertainment", "nightlife"}
                ),
                None,
            )
            if best_experience and best_experience not in selected:
                selected.append(best_experience)
        for item in candidates:
            if item not in selected:
                selected.append(item)
            if len(selected) >= 5:
                break
        return selected[:5]

    def _select_budgeted_candidates(
        self,
        candidates: list[CandidateEvidence],
        budget: int,
    ) -> list[CandidateEvidence]:
        selected: list[CandidateEvidence] = []

        def cost(items: list[CandidateEvidence]) -> int:
            return sum(item.price_per_person or 0 for item in items)

        def append_best(options: list[CandidateEvidence]) -> None:
            for item in sorted(options, key=lambda value: (value.price_per_person or 9999, -value.score)):
                if item not in selected and cost(selected) + (item.price_per_person or 0) <= budget:
                    selected.append(item)
                    return

        append_best([item for item in candidates if item.category == "restaurant"])
        append_best(
            [
                item
                for item in candidates
                if item.category in {"culture", "scenic", "entertainment", "nightlife"}
            ]
        )
        while len(selected) < 3:
            before = len(selected)
            append_best(candidates)
            if len(selected) == before:
                break
        for item in candidates:
            if len(selected) >= 5:
                break
            price = item.price_per_person or 0
            if item not in selected and cost(selected) + price <= budget:
                selected.append(item)
        return selected

    def _candidate_evidence(self, state: Any) -> list[CandidateEvidence]:
        pool = state.memory.pool
        if pool is None:
            return []
        ugc_hits = state.memory.ugc_hits or []
        ugc_by_poi: dict[str, list[dict[str, Any]]] = {}
        for hit in ugc_hits:
            ugc_by_poi.setdefault(str(hit.get("poi_id")), []).append(hit)

        candidates: list[CandidateEvidence] = []
        seen: set[str] = set()
        for category in pool.categories:
            for poi in category.pois:
                if poi.id in seen:
                    continue
                seen.add(poi.id)
                hit = (ugc_by_poi.get(poi.id) or [None])[0]
                if hit:
                    quote_ref = str(hit.get("post_id") or f"ugc:{poi.id}")
                    quote = str(hit.get("snippet") or poi.highlight_quote or poi.name)
                else:
                    quote_ref = f"pool:{poi.id}"
                    quote = poi.highlight_quote or f"{poi.name} has stable local route evidence."
                candidates.append(
                    CandidateEvidence(
                        poi_id=poi.id,
                        poi_name=poi.name,
                        category=poi.category,
                    score=poi.suitable_score,
                    price_per_person=poi.price_per_person,
                    quote_ref=quote_ref,
                    quote=quote,
                )
                )
        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates

    def _build_prompt(self, candidates: list[CandidateEvidence], state: Any) -> str:
        rows = [
            {
                "poi_id": item.poi_id,
                "name": item.poi_name,
                "category": item.category,
                "score": item.score,
                "price_per_person": item.price_per_person,
                "quote_ref": item.quote_ref,
                "quote": item.quote,
            }
            for item in candidates[:12]
        ]
        return (
            "Build a 3-5 stop route story. "
            "Return JSON with theme, narrative, stops, dropped, fallback_used. "
            f"query={state.goal.raw_query}; candidates={rows}"
        )

    def _why(self, item: CandidateEvidence, index: int) -> str:
        role = self.ROLES[min(index, len(self.ROLES) - 1)]
        return f"{item.poi_name} works as the {role}; UGC evidence: {item.quote}"

    def _theme(self, selected: list[CandidateEvidence], state: Any) -> str:
        if not selected:
            return "Route Story"
        if any(item.category == "nightlife" for item in selected):
            return "City Night Route"
        if any(item.category == "restaurant" for item in selected):
            return "Local Taste Route"
        return "Story Route"

    def _narrative(self, selected: list[CandidateEvidence], state: Any) -> str:
        names = " -> ".join(item.poi_name for item in selected[:4])
        return f"A story-led route for {state.context.city}: {names}."
