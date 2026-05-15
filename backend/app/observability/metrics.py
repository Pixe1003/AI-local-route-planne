from prometheus_client import Counter, Histogram


TOOL_LATENCY = Histogram(
    "agent_tool_latency_seconds",
    "Tool execution latency in seconds",
    labelnames=["tool_name", "status"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10, 30),
)

AGENT_RUN_LATENCY = Histogram(
    "agent_run_latency_seconds",
    "Full agent run latency",
    labelnames=["goal_kind", "phase"],
    buckets=(0.5, 1, 2, 5, 10, 30),
)

LLM_TOKENS = Counter(
    "agent_llm_tokens_total",
    "Total LLM tokens consumed",
    labelnames=["provider", "model", "kind"],
)

AMAP_REQUESTS = Counter(
    "agent_amap_requests_total",
    "Amap route requests",
    labelnames=["mode", "status", "cache"],
)

HALLUCINATION_DETECTED = Counter(
    "agent_hallucination_detected_total",
    "Hallucinated outputs blocked by post_check",
    labelnames=["specialist", "issue"],
)

CACHE_HIT_RATE = Counter(
    "agent_cache_hits_total",
    "Cache hit / miss counts",
    labelnames=["cache_name", "result"],
)

MEMORY_LAYER_USAGE = Counter(
    "agent_memory_layer_usage_total",
    "How often each memory layer contributed to a decision",
    labelnames=["layer"],
)
