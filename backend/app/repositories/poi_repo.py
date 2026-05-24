from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

from app.repositories.sqlite_poi_repo import load_sqlite_pois
from app.repositories.seed_data import load_seed_pois
from app.schemas.poi import PoiDetail


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_POI_DB_PATH = PROJECT_ROOT / "data" / "processed" / "hefei_pois.sqlite"
EXTRA_POI_DB_PATHS = [
    PROJECT_ROOT / "data" / "processed" / "hefei_scenic_pois.sqlite",
    PROJECT_ROOT / "data" / "processed" / "hefei_shopping_pois.sqlite",
]


class PoiRepository:
    def __init__(self, sqlite_path: str | Path | None = None) -> None:
        self.sqlite_path = Path(sqlite_path) if sqlite_path else DEFAULT_POI_DB_PATH
        self._pois = self._load_pois()

    def _load_pois(self) -> dict[str, PoiDetail]:
        pois = {poi.id: poi for poi in load_seed_pois()}
        db_paths = [self.sqlite_path]
        if self.sqlite_path == DEFAULT_POI_DB_PATH:
            db_paths.extend(EXTRA_POI_DB_PATHS)
        for db_path in db_paths:
            if db_path.exists():
                pois.update({poi.id: poi for poi in load_sqlite_pois(db_path)})
        return pois

    def list_by_city(self, city: str, limit: int | None = None) -> list[PoiDetail]:
        pois = [poi for poi in self._pois.values() if poi.city == city]
        return pois[:limit] if limit is not None else pois

    def get(self, poi_id: str) -> PoiDetail:
        return self._pois[poi_id]

    def get_many(self, poi_ids: Iterable[str]) -> list[PoiDetail]:
        return [self._pois[poi_id] for poi_id in poi_ids if poi_id in self._pois]

    def find_replacement(
        self,
        *,
        exclude_ids: set[str],
        category_hint: Optional[str],
        avoid_queue: bool = True,
    ) -> Optional[PoiDetail]:
        candidates = [poi for poi in self._pois.values() if poi.id not in exclude_ids]
        if category_hint:
            same_category = [poi for poi in candidates if poi.category == category_hint]
            if same_category:
                candidates = same_category
        if avoid_queue:
            candidates.sort(key=lambda poi: (poi.queue_estimate["weekend_peak"], -poi.rating))
        else:
            candidates.sort(key=lambda poi: (-poi.rating, poi.queue_estimate["weekend_peak"]))
        return candidates[0] if candidates else None


@lru_cache
def get_poi_repository() -> PoiRepository:
    return PoiRepository()
