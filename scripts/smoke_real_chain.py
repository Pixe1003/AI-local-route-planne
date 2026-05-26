from __future__ import annotations

import argparse
import json
import sys
from urllib import request


def _get_json(base_url: str, path: str) -> dict:
    with request.urlopen(f"{base_url.rstrip('/')}{path}", timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(base_url: str, path: str, payload: dict) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--query",
        default="今天 14:00 到 20:00 在合肥从三孝口出发，情侣想少排队吃本地菜顺路拍照",
    )
    args = parser.parse_args()

    health = _get_json(args.base_url, "/health")
    integrations = _get_json(args.base_url, "/api/meta/integrations")
    profile = _post_json(
        args.base_url,
        "/api/onboarding/profile",
        {"query": args.query, "answers": {}},
    )["profile"]
    pool = _post_json(
        args.base_url,
        "/api/pool/generate",
        {
            "user_id": "mock_user",
            "city": "hefei",
            "date": "2026-05-26",
            "need_profile": profile,
        },
    )
    plan = _post_json(
        args.base_url,
        "/api/plan/generate",
        {
            "pool_id": pool["pool_id"],
            "selected_poi_ids": pool["default_selected_ids"],
            "need_profile": profile,
        },
    )["plans"][0]

    categories = {stop["category"] for stop in plan["stops"]}
    checks = {
        "rag_collection_count": health.get("rag", {}).get("collection_count", 0),
        "embedding_configured": integrations["embedding"],
        "llm_configured": integrations["llm"],
        "amap_configured": integrations["amap"],
        "route_valid": plan["summary"]["validation"]["is_valid"],
        "has_restaurant": "restaurant" in categories,
        "has_experience": bool(
            categories & {"culture", "scenic", "shopping", "entertainment", "nightlife", "outdoor"}
        ),
    }
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    hard_failures = [
        name
        for name in ["route_valid", "has_restaurant", "has_experience"]
        if not checks[name]
    ]
    return 1 if hard_failures else 0


if __name__ == "__main__":
    sys.exit(main())
