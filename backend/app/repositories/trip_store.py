import sqlite3
from pathlib import Path

from app.config import get_settings
from app.schemas.trip import TripRecord


class TripStore:
    def __init__(self, path: str | Path | None = None) -> None:
        configured = path or get_settings().app_state_sqlite_path
        self.path = Path(configured)
        if not self.path.is_absolute():
            project_root = Path(__file__).resolve().parents[3]
            self.path = project_root / self.path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute(
                """
                create table if not exists trips (
                    trip_id text primary key,
                    user_id text not null,
                    updated_at text not null,
                    payload text not null
                )
                """
            )
            con.execute("create index if not exists idx_trips_user_updated on trips(user_id, updated_at)")

    def get(self, trip_id: str) -> TripRecord | None:
        with self._connect() as con:
            row = con.execute("select payload from trips where trip_id = ?", (trip_id,)).fetchone()
        return TripRecord.model_validate_json(row[0]) if row else None

    def list_by_user(self, user_id: str) -> list[TripRecord]:
        with self._connect() as con:
            rows = con.execute(
                """
                select payload from trips
                where user_id = ?
                order by updated_at desc
                """,
                (user_id,),
            ).fetchall()
        return [TripRecord.model_validate_json(row[0]) for row in rows]

    def upsert(self, trip: TripRecord) -> None:
        with self._connect() as con:
            con.execute(
                """
                insert into trips(trip_id, user_id, updated_at, payload)
                values(?, ?, ?, ?)
                on conflict(trip_id) do update set
                    user_id = excluded.user_id,
                    updated_at = excluded.updated_at,
                    payload = excluded.payload
                """,
                (
                    trip.trip_id,
                    trip.user_id,
                    trip.summary.updated_at.isoformat(),
                    trip.model_dump_json(),
                ),
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, check_same_thread=False)
