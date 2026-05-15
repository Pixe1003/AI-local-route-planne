from datetime import datetime, timezone
import threading
import time

import numpy as np

from app.agent.session_summarizer import summarize_session
from app.agent.state import AgentGoal, AgentState
from app.agent.story_models import StoryPlan, StoryStop
from app.agent.conductor import Conductor
from app.agent.tools import get_tool_registry
from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import PlanContext
from app.schemas.pool import TimeWindow


def _state(*, session_id: str, user_id: str = "vector_user", query: str = "想吃火锅") -> AgentState:
    context = PlanContext(
        city="hefei",
        date="2026-05-10",
        time_window=TimeWindow(start="18:00", end="22:00"),
        party="friends",
        budget_per_person=160,
    )
    state = AgentState(
        goal=AgentGoal(
            raw_query=query,
            session_id=session_id,
            user_id=user_id,
            locale_city="hefei",
        ),
        profile=UserNeedProfile.from_plan_context(context, raw_query=query),
        context=context,
        phase="DONE",
    )
    state.memory.story_plan = StoryPlan(
        theme="Hotpot Route" if "火锅" in query else "Cafe Route",
        narrative=query,
        stops=[
            StoryStop(
                poi_id="hf_poi_061581",
                role="opener",
                why="opener",
                ugc_quote_ref="ugc:1",
                ugc_quote="evidence",
            ),
            StoryStop(
                poi_id="hf_poi_035366",
                role="main",
                why="main",
                ugc_quote_ref="ugc:2",
                ugc_quote="evidence",
            ),
            StoryStop(
                poi_id="hf_poi_020889",
                role="closer",
                why="closer",
                ugc_quote_ref="ugc:3",
                ugc_quote="evidence",
            ),
        ],
    )
    return state


def _fake_encode(text: str) -> np.ndarray:
    if "火锅" in text or "Hotpot" in text:
        return np.asarray([1.0, 0.0], dtype="float32")
    return np.asarray([0.0, 1.0], dtype="float32")


def test_add_and_search_session_returns_similar_hit(tmp_path, monkeypatch) -> None:
    from app.agent.session_summarizer import summarize_session
    from app.repositories.session_vector_repo import SessionVectorRepo

    repo = SessionVectorRepo(sessions_dir=tmp_path)
    monkeypatch.setattr(repo, "_encode", _fake_encode)

    state = _state(session_id="s1", query="想吃火锅")
    repo.add_session(state, summarize_session(state))

    hits = repo.search_similar("vector_user", "火锅", top_k=2)

    assert hits
    assert hits[0].session_id == "s1"
    assert hits[0].theme == "Hotpot Route"
    assert hits[0].similarity > 0.9


def test_search_excludes_current_session_and_deduplicates(tmp_path, monkeypatch) -> None:
    from app.agent.session_summarizer import summarize_session
    from app.repositories.session_vector_repo import SessionVectorRepo

    repo = SessionVectorRepo(sessions_dir=tmp_path)
    monkeypatch.setattr(repo, "_encode", _fake_encode)

    state = _state(session_id="s1", query="想吃火锅")
    summary = summarize_session(state)
    repo.add_session(state, summary)
    repo.add_session(state, summary)

    hits = repo.search_similar(
        "vector_user",
        "火锅",
        top_k=3,
        exclude_session_id="s1",
    )

    assert hits == []
    assert (tmp_path / "vector_user.meta.jsonl").read_text(encoding="utf-8").count("s1") == 1


def test_search_returns_empty_for_new_user(tmp_path, monkeypatch) -> None:
    from app.repositories.session_vector_repo import SessionVectorRepo

    repo = SessionVectorRepo(sessions_dir=tmp_path)
    monkeypatch.setattr(repo, "_encode", _fake_encode)

    assert repo.search_similar("never_seen", "anything") == []


def test_conductor_recall_tool_appears_in_registry() -> None:
    from app.agent.tools import get_tool_registry

    names = {tool["name"] for tool in get_tool_registry().schemas_for_llm()}

    assert "recall_similar_sessions" in names


def test_rule_based_decision_recalls_similar_sessions_before_ugc_search() -> None:
    state = _state(session_id="current", query="hotpot again")
    state.memory.intent = {"parsed": True}
    state.memory.episodic_summary = [summarize_session(_state(session_id="past"))]
    state.memory.similar_sessions_searched = False
    state.memory.ugc_searched = False

    decision = Conductor(get_tool_registry(), llm=object())._rule_based_decision(state)

    assert decision.tool == "recall_similar_sessions"
    assert decision.args == {"query": "hotpot again", "top_k": 3}


def test_similar_session_hit_accepts_timezone_aware_created_at() -> None:
    from app.schemas.user_memory import SimilarSessionHit

    hit = SimilarSessionHit(
        session_id="s1",
        raw_query="火锅",
        theme="Hotpot Route",
        similarity=0.8,
        stop_poi_names=["金巷子老火锅"],
        days_ago=(datetime.now(timezone.utc) - datetime.now(timezone.utc)).days,
    )

    assert hit.session_id == "s1"


def test_add_session_serializes_same_user_persist(tmp_path, monkeypatch) -> None:
    from app.repositories.session_vector_repo import SessionVectorRepo

    repo = SessionVectorRepo(sessions_dir=tmp_path)
    monkeypatch.setattr(repo, "_encode", _fake_encode)

    original_persist = repo._persist
    active_persists = 0
    overlapped = False
    persist_lock = threading.Lock()

    def observing_persist(user_id, index, metas):
        nonlocal active_persists, overlapped
        with persist_lock:
            active_persists += 1
            if active_persists > 1:
                overlapped = True
        try:
            time.sleep(0.05)
            original_persist(user_id, index, metas)
        finally:
            with persist_lock:
                active_persists -= 1

    monkeypatch.setattr(repo, "_persist", observing_persist)

    start = threading.Barrier(2)
    errors: list[BaseException] = []

    def worker(state: AgentState) -> None:
        try:
            start.wait(timeout=1)
            repo.add_session(state, summarize_session(state))
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(_state(session_id="s1", query="hotpot one"),)),
        threading.Thread(target=worker, args=(_state(session_id="s2", query="hotpot two"),)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    assert errors == []
    assert not overlapped
    meta_text = (tmp_path / "vector_user.meta.jsonl").read_text(encoding="utf-8")
    assert meta_text.count('"session_id": "s1"') == 1
    assert meta_text.count('"session_id": "s2"') == 1
