from typing import Any

from app.agent.state import Critique


class Critic:
    def review(self, state: Any) -> Critique:
        story = state.memory.story_plan
        validation = state.memory.validation
        issues: list[str] = []

        if story is None:
            issues.append("story_missing")
            return self._critique(issues, should_stop=False)

        if not story.theme:
            issues.append("theme_missing")
        if not story.narrative:
            issues.append("narrative_missing")
        if not 3 <= len(story.stops) <= 5:
            issues.append("invalid_stop_count")
        if any(not stop.ugc_quote_ref or not stop.ugc_quote for stop in story.stops):
            issues.append("weak_evidence")

        if validation is not None and not validation.is_valid:
            issues.extend(issue.code for issue in validation.issues)

        should_stop = not issues
        return self._critique(issues, should_stop=should_stop, story=story)

    def _critique(
        self,
        issues: list[str],
        *,
        should_stop: bool,
        story: Any | None = None,
    ) -> Critique:
        stop_count = len(story.stops) if story else 0
        evidence_ok = story is not None and all(stop.ugc_quote_ref and stop.ugc_quote for stop in story.stops)
        return Critique(
            theme_coherence=8 if story and story.theme else 4,
            evidence_strength=8 if evidence_ok else 4,
            pacing=8 if 3 <= stop_count <= 5 else 4,
            preference_fit=7 if story else 4,
            narrative=8 if story and story.narrative else 4,
            should_stop=should_stop,
            hint=None if should_stop else "revise_story_or_route",
            issues=list(dict.fromkeys(issues)),
        )
