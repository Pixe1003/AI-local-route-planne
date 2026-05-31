"""Measure end-to-end and per-tool latency of POST /api/agent/run.

What it does
============

Runs each scenario under `backend/eval/scenarios/` N times per decision mode and
records:

- E2E latency (HTTP entry -> response): p50/p95/p99/min/max/mean
- Per-tool latency (from response.steps[].latency_ms): mean per tool
- Cold start (first call) vs warm (subsequent calls)
- Advisory, non-gating thresholds for warm p95 and cold-start ratio
- Startup warmup is invoked once at bench start (via `run_startup_warmup`)
  so the FAISS / sentence-transformer / ranker model load does NOT pollute
  the first cold measurement. Without this, TestClient(app) used without
  context manager would skip the FastAPI lifespan and the very first scenario
  would absorb ~120 s of model loading.
- Decision mode comparison:
    * rule = `agent_fast_decision_enabled=True`
      Conductor selects next tool via rule-based decision (no LLM call).
    * llm  = `agent_fast_decision_enabled=False`
      Conductor asks the LLM via function calling.
      Without an LLM key configured, this internally falls back to the rule
      path inside `LlmClient.complete_tool_call`, so numbers will resemble
      rule mode -- the report notes this.

The Amap route client is patched to a deterministic stub (same as
`backend/eval/run_eval.py`) so measurements reflect the Agent + solver
critical path, not external network jitter.

Usage
=====

    # default: rule + llm, 5 repeats per scenario, output to data/eval/latency_report.md
    python scripts/bench_latency.py

    # quicker smoke
    python scripts/bench_latency.py --repeats 2

    # only one mode (e.g. CI)
    python scripts/bench_latency.py --modes rule --repeats 3

    # serious tail-latency measurement
    python scripts/bench_latency.py --repeats 30
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# Make settings deterministic regardless of host .env, mirroring eval/run_eval.py.
os.environ.setdefault("LOCAL_ROUTE_DISABLE_ENV_FILE", "1")
os.environ.setdefault("PYTHONPATH", str(BACKEND))

WARM_P95_TARGET_MS = 4500.0
COLD_TO_WARM_P95_TARGET = 3.0


def main() -> None:
    parser = argparse.ArgumentParser(description="AIroute response-time bench")
    parser.add_argument(
        "--scenarios",
        default=str(BACKEND / "eval" / "scenarios"),
        help="Directory of scenario YAML/JSON files (default: backend/eval/scenarios)",
    )
    parser.add_argument(
        "--out",
        default="data/eval/latency_report.md",
        help="Output markdown report path (default: data/eval/latency_report.md)",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=5,
        help="Repeats per (mode, scenario) cell (default: 5). First repeat is the cold call.",
    )
    parser.add_argument(
        "--modes",
        default="rule,llm",
        help="Comma-separated decision modes to compare: rule, llm (default: both)",
    )
    args = parser.parse_args()

    _patch_local_amap_client()
    _run_startup_warmup_once()

    scenarios = _load_scenarios(Path(args.scenarios))
    if not scenarios:
        raise SystemExit(f"No scenarios found in {args.scenarios}")

    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    for mode in modes:
        if mode not in {"rule", "llm"}:
            raise SystemExit(f"Unknown mode '{mode}'. Allowed: rule, llm")

    results: dict[tuple[str, str], dict[str, Any]] = {}

    for mode in modes:
        print(f"=== Mode: {mode} ===")
        _set_decision_mode(mode)
        _clear_process_caches()
        client = _build_client()
        for scenario in scenarios:
            sid = scenario["id"]
            print(f"  scenario={sid} repeats={args.repeats}", flush=True)
            results[(mode, sid)] = _measure_scenario(client, scenario, args.repeats)

    report = _render_report(results, modes, scenarios, args.repeats)
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"\nWrote latency report to {out}")


# ---------- Decision-mode toggling ----------------------------------------


def _set_decision_mode(mode: str) -> None:
    """Flip agent_fast_decision_enabled and force settings reload."""
    if mode == "rule":
        os.environ["AGENT_FAST_DECISION_ENABLED"] = "true"
    elif mode == "llm":
        os.environ["AGENT_FAST_DECISION_ENABLED"] = "false"
    os.environ.setdefault("AGENT_TOOL_CALLING_ENABLED", "true")

    from app.config import get_settings

    get_settings.cache_clear()
    # touch to validate the override took effect
    settings = get_settings()
    assert (settings.agent_fast_decision_enabled is True) == (mode == "rule"), (
        f"Settings did not pick up AGENT_FAST_DECISION_ENABLED override for mode={mode}"
    )


def _clear_process_caches() -> None:
    """Clear lru_caches that materially affect cold-start measurement."""
    try:
        from app.ml.ranker import get_ranker

        get_ranker.cache_clear()
    except Exception:
        pass
    try:
        from app.repositories.poi_repo import get_poi_repository

        get_poi_repository.cache_clear()
    except Exception:
        pass


def _build_client():
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)


# ---------- Measurement ---------------------------------------------------


def _measure_scenario(client, scenario: dict[str, Any], repeats: int) -> dict[str, Any]:
    e2e_ms: list[float] = []
    per_iter_tool_latencies: list[dict[str, list[int]]] = []

    for i in range(repeats):
        start = time.perf_counter()
        response = client.post("/api/agent/run", json=scenario["request"])
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        if response.status_code != 200:
            print(f"    iter={i} status={response.status_code} body={response.text[:160]}")
            per_iter_tool_latencies.append({})
            continue

        e2e_ms.append(elapsed_ms)
        payload = response.json()
        tool_map: dict[str, list[int]] = defaultdict(list)
        for step in payload.get("steps", []):
            name = step.get("tool_name")
            lat = step.get("latency_ms")
            if name and isinstance(lat, (int, float)):
                tool_map[name].append(int(lat))
        per_iter_tool_latencies.append(dict(tool_map))

    cold_ms = e2e_ms[0] if e2e_ms else None
    warm_ms = e2e_ms[1:] if len(e2e_ms) > 1 else []
    return {
        "e2e_all_ms": e2e_ms,
        "cold_ms": cold_ms,
        "warm_ms": warm_ms,
        "tool_latencies_per_iter": per_iter_tool_latencies,
    }


# ---------- Stats ---------------------------------------------------------


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def _stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "p50": None, "p95": None, "p99": None, "min": None, "max": None, "mean": None}
    return {
        "n": len(values),
        "p50": round(_percentile(values, 50) or 0.0, 1),
        "p95": round(_percentile(values, 95) or 0.0, 1),
        "p99": round(_percentile(values, 99) or 0.0, 1),
        "min": round(min(values), 1),
        "max": round(max(values), 1),
        "mean": round(statistics.mean(values), 1),
    }


def _format_or_dash(value: Any, fmt: str = "{:.0f}") -> str:
    if value is None:
        return "—"
    return fmt.format(value)


def _pass_warn(condition: bool | None) -> str:
    if condition is None:
        return "N/A"
    return "PASS" if condition else "WARN"


# ---------- Reporting -----------------------------------------------------


def _render_report(
    results: dict[tuple[str, str], dict[str, Any]],
    modes: list[str],
    scenarios: list[dict[str, Any]],
    repeats: int,
) -> str:
    llm_key_present = bool(os.environ.get("LLM_API_KEY"))
    lines: list[str] = [
        "# AIroute · Response-Time Bench",
        "",
        f"- Generated: `{time.strftime('%Y-%m-%d %H:%M:%S')}`",
        f"- Scenarios: {len(scenarios)} (from `backend/eval/scenarios/`)",
        f"- Repeats per (mode, scenario): **{repeats}** (first call = cold; rest = warm)",
        f"- Modes compared: {', '.join(f'`{m}`' for m in modes)}",
        f"- LLM API key configured: **{'yes' if llm_key_present else 'no — `llm` mode falls back to rule path inside LlmClient'}**",
        "- Amap route client: deterministic stub (same patch as `backend/eval/run_eval.py`)",
        "",
        "## 1. E2E summary (warm, all scenarios pooled)",
        "",
        "| Mode | n | p50 (ms) | p95 (ms) | p99 (ms) | min | max | mean |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for mode in modes:
        pooled: list[float] = []
        for scenario in scenarios:
            pooled.extend(results[(mode, scenario["id"])]["warm_ms"])
        s = _stats(pooled)
        lines.append(
            "| {mode} | {n} | {p50} | {p95} | {p99} | {mn} | {mx} | {mean} |".format(
                mode=mode,
                n=s["n"],
                p50=_format_or_dash(s["p50"], "{:.0f}"),
                p95=_format_or_dash(s["p95"], "{:.0f}"),
                p99=_format_or_dash(s["p99"], "{:.0f}"),
                mn=_format_or_dash(s["min"], "{:.0f}"),
                mx=_format_or_dash(s["max"], "{:.0f}"),
                mean=_format_or_dash(s["mean"], "{:.0f}"),
            )
        )

    lines.extend([
        "",
        "## 2. Cold start (first call per scenario, per mode)",
        "",
        "| Scenario | " + " | ".join(f"`{m}` cold (ms)" for m in modes) + " |",
        "| --- | " + " | ".join("---:" for _ in modes) + " |",
    ])
    for scenario in scenarios:
        sid = scenario["id"]
        cells = [_format_or_dash(results[(m, sid)]["cold_ms"], "{:.0f}") for m in modes]
        lines.append(f"| {sid} | " + " | ".join(cells) + " |")

    lines.extend([
        "",
        "## 3. Per-scenario E2E (warm)",
        "",
        "| Scenario | Mode | n | p50 | p95 | mean |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ])
    for scenario in scenarios:
        sid = scenario["id"]
        for mode in modes:
            s = _stats(results[(mode, sid)]["warm_ms"])
            lines.append(
                "| {sid} | `{mode}` | {n} | {p50} | {p95} | {mean} |".format(
                    sid=sid,
                    mode=mode,
                    n=s["n"],
                    p50=_format_or_dash(s["p50"], "{:.0f}"),
                    p95=_format_or_dash(s["p95"], "{:.0f}"),
                    mean=_format_or_dash(s["mean"], "{:.0f}"),
                )
            )

    lines.extend([
        "",
        "## 4. Per-tool latency (warm only, mean ms · sample count)",
        "",
    ])
    lines.append(
        "| Tool | "
        + " | ".join(f"`{m}` mean (ms)" for m in modes)
        + " | "
        + " | ".join(f"`{m}` n" for m in modes)
        + " |"
    )
    lines.append(
        "| --- | "
        + " | ".join("---:" for _ in modes)
        + " | "
        + " | ".join("---:" for _ in modes)
        + " |"
    )

    all_tools: set[str] = set()
    for mode in modes:
        for scenario in scenarios:
            for tool_map in results[(mode, scenario["id"])]["tool_latencies_per_iter"][1:]:
                all_tools.update(tool_map.keys())

    for tool in sorted(all_tools):
        means: list[str] = []
        counts: list[str] = []
        for mode in modes:
            samples: list[int] = []
            for scenario in scenarios:
                per_iter = results[(mode, scenario["id"])]["tool_latencies_per_iter"]
                # skip first iter (cold)
                for tool_map in per_iter[1:]:
                    samples.extend(tool_map.get(tool, []))
            if samples:
                means.append(f"{statistics.mean(samples):.0f}")
                counts.append(str(len(samples)))
            else:
                means.append("—")
                counts.append("0")
        lines.append("| {t} | {m} | {c} |".format(t=tool, m=" | ".join(means), c=" | ".join(counts)))

    lines.extend([
        "",
        "## 5. Advisory thresholds (non-gating)",
        "",
        "- These thresholds are guidance for reading the report; the script does not fail",
        "  when a benchmark crosses them.",
        f"- Target: warm p95 <= {WARM_P95_TARGET_MS:.0f} ms.",
        f"- Target: cold <= warm p95 x {COLD_TO_WARM_P95_TARGET:.0f}.",
    ])
    if repeats < 20:
        lines.append(
            f"- p99 is weak with `repeats={repeats}`; raise to `--repeats 20` or higher"
            " for serious tail-latency claims."
        )
    else:
        lines.append(
            f"- `repeats={repeats}` gives enough samples for p99 to be more useful, though"
            " production traffic is still the stronger source for tail-latency promises."
        )
    lines.extend([
        "",
        "| Mode | warm p95 status | cold ratio status | warm p95 (ms) | max cold (ms) | cold limit (ms) |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ])
    for mode in modes:
        pooled_warm: list[float] = []
        cold_values: list[float] = []
        for scenario in scenarios:
            result = results[(mode, scenario["id"])]
            pooled_warm.extend(result["warm_ms"])
            if result["cold_ms"] is not None:
                cold_values.append(float(result["cold_ms"]))
        warm_p95 = _stats(pooled_warm)["p95"]
        max_cold = max(cold_values) if cold_values else None
        cold_limit = (warm_p95 * COLD_TO_WARM_P95_TARGET) if warm_p95 is not None else None
        lines.append(
            "| {mode} | {warm_status} | {cold_status} | {warm_p95} | {max_cold} | {cold_limit} |".format(
                mode=mode,
                warm_status=_pass_warn(warm_p95 <= WARM_P95_TARGET_MS if warm_p95 is not None else None),
                cold_status=_pass_warn(
                    max_cold <= cold_limit if max_cold is not None and cold_limit is not None else None
                ),
                warm_p95=_format_or_dash(warm_p95, "{:.0f}"),
                max_cold=_format_or_dash(max_cold, "{:.0f}"),
                cold_limit=_format_or_dash(cold_limit, "{:.0f}"),
            )
        )

    lines.extend([
        "",
        "## 6. How to read this report",
        "",
        "- **Cold** is the very first call after caches are cleared; it includes one-time costs",
        "  like loading the LightGBM model, opening FAISS / SQLite, and JIT setup for the solver.",
        "- **Warm** is every subsequent call. This is the latency users feel after the service",
        "  has been serving traffic for a while.",
        "- **`rule` mode** lets the Conductor pick the next tool from in-process rules; **no**",
        "  LLM HTTP call is made during decision making.",
        "- **`llm` mode** asks the LLM (function calling) for the next tool. If no `LLM_API_KEY`",
        "  is set, the LLM client falls back to a deterministic fallback, so timings will look",
        "  similar to `rule` mode.",
        "- The per-tool table aggregates **only warm iterations**. If a tool appears under `rule`",
        "  but not `llm` (or vice versa), the decision policy in that mode skipped it.",
        "",
        "## 7. Known caveats",
        "",
        "- Amap is stubbed deterministically, so `get_amap_chain` latency reflects local",
        "  serialization only. To benchmark real Amap, remove `_patch_local_amap_client()`.",
        "- LightGBM model is cleared once per mode switch via `get_ranker.cache_clear()`, but",
        "  FAISS / sentence-transformer model handles are process-global and cannot be unloaded;",
        "  cold here means \"cold for the agent state machine\", not \"cold for the OS\".",
        "- Treat p99 as an exploratory signal unless `--repeats` is high enough for the",
        "  tail sample to be meaningful.",
        "",
    ])

    return "\n".join(lines) + "\n"


# ---------- IO helpers ----------------------------------------------------


def _load_scenarios(path: Path) -> list[dict[str, Any]]:
    import yaml

    scenarios: list[dict[str, Any]] = []
    for file in sorted(path.glob("*")):
        if file.suffix.lower() in {".yaml", ".yml"}:
            scenarios.append(yaml.safe_load(file.read_text(encoding="utf-8")))
        elif file.suffix.lower() == ".json":
            scenarios.append(json.loads(file.read_text(encoding="utf-8")))
    return scenarios


def _run_startup_warmup_once() -> None:
    """Trigger the OPT-2 warmup probe before any timed call.

    bench_latency.py uses ``TestClient(app)`` without a context manager, so
    Starlette does NOT execute the FastAPI ``lifespan``. Without this call,
    the very first scenario absorbs the one-time ~120 s cost of loading
    bge-small-zh / FAISS / LightGBM, badly distorting cold-start numbers.

    Failure is non-fatal: if the import or warmup itself fails the bench
    continues and the cold measurements will just look as before.
    """
    try:
        from app.config import get_settings
        from app.main import run_startup_warmup
    except Exception as exc:  # pragma: no cover - defensive
        print(f"  startup warmup unavailable, skipping: {exc}")
        return

    settings = get_settings()
    if not getattr(settings, "startup_warmup_enabled", False):
        print("  startup_warmup_enabled=false, skipping warmup")
        return

    print("Running startup warmup (FAISS / sentence-transformer / ranker / POI repo)...", flush=True)
    started = time.perf_counter()
    run_startup_warmup(settings)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    print(f"  warmup done in {elapsed_ms:.0f} ms")


def _patch_local_amap_client() -> None:
    """Stub the Amap route client so latency reflects in-process work only.

    Mirrors `_patch_local_route_client()` from `backend/eval/run_eval.py` so
    bench numbers can be directly compared with the offline eval report.
    """
    from app.api import routes_route
    from app.services.amap.schemas import AmapRouteMode, AmapRouteResult, AmapRouteStep

    class _LocalRouteClient:
        def get_route(self, **kwargs: Any) -> AmapRouteResult:
            return AmapRouteResult(
                mode=AmapRouteMode.DRIVING,
                distance_m=1000,
                duration_s=600,
                steps=[
                    AmapRouteStep(
                        instruction="bench eval segment",
                        road_name="bench",
                        distance_m=1000,
                        duration_s=600,
                        polyline_coordinates=[],
                    )
                ],
                polyline_coordinates=[],
                raw_response={"bench": True},
            )

        def close(self) -> None:
            return None

    routes_route.AmapRouteClient = _LocalRouteClient  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()
