"""Seed a few demo agent sessions so memory panels have content immediately."""

from __future__ import annotations

import os
import time

import httpx


BASE_URL = os.getenv("AIROUTE_API_BASE_URL", "http://localhost:8000").rstrip("/")
DEMO_QUERIES = [
    {"user_id": "demo_user", "free_text": "想吃合肥本地菜，少排队", "budget_per_person": 150},
    {"user_id": "demo_user", "free_text": "和朋友吃火锅，预算高一点", "budget_per_person": 250},
    {"user_id": "demo_user", "free_text": "下午找个安静咖啡", "budget_per_person": 80},
    {"user_id": "demo_user", "free_text": "想再试试本地特色", "budget_per_person": 180},
]


def main() -> None:
    for index, query in enumerate(DEMO_QUERIES, start=1):
        print(f"[{index}/{len(DEMO_QUERIES)}] {query['free_text']}")
        response = httpx.post(
            f"{BASE_URL}/api/agent/run",
            json={
                **query,
                "city": "hefei",
                "date": "2026-05-08",
                "time_window": {"start": "14:00", "end": "20:00"},
            },
            timeout=60,
        )
        response.raise_for_status()
        time.sleep(1)

    facts = httpx.get(
        f"{BASE_URL}/api/agent/user/demo_user/facts",
        params={"force_refresh": "true"},
        timeout=20,
    )
    facts.raise_for_status()
    payload = facts.json()
    print(
        "\nWarmed up. "
        f"Facts: session_count={payload['session_count']}, "
        f"favorite_categories={payload['favorite_categories']}"
    )


if __name__ == "__main__":
    main()
