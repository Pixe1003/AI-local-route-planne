import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.services.amap.schemas import AmapRouteMode, AmapRouteResult, AmapRouteStep


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DB_PATH = PROJECT_ROOT / "data" / "processed" / "amap_cache.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS amap_segments (
    cache_key TEXT PRIMARY KEY,
    distance_m REAL NOT NULL,
    duration_s REAL,
    steps_json TEXT NOT NULL,
    raw_response_json TEXT NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_hit_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_amap_segments_updated ON amap_segments(updated_at DESC);
"""


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn


def cache_key(
    *,
    mode: str,
    origin_lon: float,
    origin_lat: float,
    dest_lon: float,
    dest_lat: float,
) -> str:
    return f"{mode}:{origin_lon:.6f},{origin_lat:.6f}->{dest_lon:.6f},{dest_lat:.6f}"


def get_cached(key: str) -> AmapRouteResult | None:
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT distance_m, duration_s, steps_json, raw_response_json
            FROM amap_segments
            WHERE cache_key = ?
            """,
            (key,),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            """
            UPDATE amap_segments
            SET hit_count = hit_count + 1, last_hit_at = ?
            WHERE cache_key = ?
            """,
            (datetime.now(timezone.utc).isoformat(), key),
        )

    steps_data = json.loads(row[2])
    steps = [AmapRouteStep(**item) for item in steps_data]
    return AmapRouteResult(
        mode=AmapRouteMode(key.split(":", 1)[0]),
        distance_m=float(row[0]),
        duration_s=float(row[1]) if row[1] is not None else None,
        steps=steps,
        polyline_coordinates=[
            coordinate
            for step in steps
            for coordinate in step.polyline_coordinates
        ],
        raw_response=json.loads(row[3]) if row[3] else {},
    )


def set_cached(key: str, result: AmapRouteResult) -> None:
    now = datetime.now(timezone.utc).isoformat()
    steps_data = [
        {
            "instruction": step.instruction,
            "road_name": step.road_name,
            "distance_m": step.distance_m,
            "duration_s": step.duration_s,
            "polyline_coordinates": step.polyline_coordinates,
        }
        for step in result.steps
    ]
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO amap_segments
                (cache_key, distance_m, duration_s, steps_json, raw_response_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                distance_m = excluded.distance_m,
                duration_s = excluded.duration_s,
                steps_json = excluded.steps_json,
                raw_response_json = excluded.raw_response_json,
                updated_at = excluded.updated_at
            """,
            (
                key,
                result.distance_m,
                result.duration_s,
                json.dumps(steps_data, ensure_ascii=False),
                json.dumps(result.raw_response, ensure_ascii=False),
                now,
            ),
        )


def clear() -> None:
    if not DB_PATH.exists():
        return
    with _conn() as conn:
        conn.execute("DELETE FROM amap_segments")
