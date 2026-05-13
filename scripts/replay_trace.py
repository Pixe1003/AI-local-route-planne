import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.agent.store import load_state  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a persisted AIroute agent trace.")
    parser.add_argument("session_id")
    args = parser.parse_args()

    state = load_state(args.session_id)
    if state is None:
        print(f"No session: {args.session_id}")
        return

    print(f"Goal: {state.goal.kind} | {state.goal.raw_query}")
    print(f"Phase: {state.phase}")
    print(f"Trace: {state.trace_id}")
    print(f"Steps ({len(state.steps)}):")
    for index, step in enumerate(state.steps, start=1):
        print(
            f"  [{index:>2}] {step.latency_ms:>5} ms | "
            f"{step.tool_name:<25} | {step.observation_summary or ''}"
        )
    if state.memory.critique:
        critique = state.memory.critique
        print(
            f"\nCritique: stop={critique.should_stop} | "
            f"theme={critique.theme_coherence} | evidence={critique.evidence_strength}"
        )


if __name__ == "__main__":
    main()
