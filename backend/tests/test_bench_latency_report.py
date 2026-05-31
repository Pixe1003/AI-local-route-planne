from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_bench_latency_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "bench_latency.py"
    spec = importlib.util.spec_from_file_location("bench_latency", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_latency_report_includes_advisory_thresholds_and_p99_warning() -> None:
    bench_latency = _load_bench_latency_module()
    scenarios = [{"id": "fast"}, {"id": "slow"}]
    modes = ["rule", "llm"]
    results = {
        ("rule", "fast"): {
            "cold_ms": 1500.0,
            "warm_ms": [900.0, 1000.0, 1100.0],
            "tool_latencies_per_iter": [
                {"parse_intent": [10]},
                {"parse_intent": [8], "recommend_pool": [120]},
                {"parse_intent": [9], "recommend_pool": [130]},
                {"parse_intent": [8], "recommend_pool": [125]},
            ],
        },
        ("rule", "slow"): {
            "cold_ms": 16000.0,
            "warm_ms": [4600.0, 4800.0, 5000.0],
            "tool_latencies_per_iter": [
                {"parse_intent": [10]},
                {"parse_intent": [8], "solve_constrained_route": [900]},
                {"parse_intent": [9], "solve_constrained_route": [950]},
                {"parse_intent": [8], "solve_constrained_route": [1000]},
            ],
        },
        ("llm", "fast"): {
            "cold_ms": 1800.0,
            "warm_ms": [1000.0, 1200.0, 1400.0],
            "tool_latencies_per_iter": [
                {"parse_intent": [10]},
                {"parse_intent": [8]},
                {"parse_intent": [9]},
                {"parse_intent": [8]},
            ],
        },
        ("llm", "slow"): {
            "cold_ms": 2200.0,
            "warm_ms": [1600.0, 1800.0, 2000.0],
            "tool_latencies_per_iter": [
                {"parse_intent": [10]},
                {"parse_intent": [8]},
                {"parse_intent": [9]},
                {"parse_intent": [8]},
            ],
        },
    }

    report = bench_latency._render_report(results, modes, scenarios, repeats=5)

    assert "## 5. Advisory thresholds (non-gating)" in report
    assert "warm p95 <= 4500 ms" in report
    assert "cold <= warm p95 x 3" in report
    assert "| rule | WARN | WARN |" in report
    assert "| llm | PASS | PASS |" in report
    assert "p99 is weak with `repeats=5`; raise to `--repeats 20` or higher" in report
