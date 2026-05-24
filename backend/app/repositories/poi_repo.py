from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

from app.config import get_settings
from app.repositories.seed_data import load_seed_pois
from app.repositories.sqlite_poi_repo import load_sqlite_poi, load_sqlite_pois
from app.schemas.poi import PoiDetail


class PoiRepository:
    def __init__(self, sqlite_path: str | Path | None = None) -> None:
        self._seed_pois = {poi.id: poi for poi in load_seed_pois()}
        self._sqlite_path = Path(sqlite_path) if sqlite_path is not None else self._default_sqlite_path()
        self._sqlite_pois: dict[str, PoiDetail] | None = None

    def list_by_city(self, city: str, limit: int | None = None) -> list[PoiDetail]:
        pois = [poi for poi in self._seed_pois.values() if poi.city == city]
        if city == "hefei":
            if limit is None:
                pois.extend(poi for poi in self._load_sqlite_pois().values() if poi.city == city)
            else:
                remaining = max(0, limit - len(pois))
                if remaining:
                    pois.extend(load_sqlite_pois(self._sqlite_path, city, remaining))
                return pois[:limit]
        return pois[:limit] if limit is not None else pois

    def get(self, poi_id: str) -> PoiDetail:
        if poi_id in self._seed_pois:
            return self._seed_pois[poi_id]
        if self._sqlite_pois is not None and poi_id in self._sqlite_pois:
            return self._sqlite_pois[poi_id]
        poi = load_sqlite_poi(self._sqlite_path, poi_id)
        if poi is not None:
            return poi
        raise KeyError(poi_id)

    def get_many(self, poi_ids: Iterable[str]) -> list[PoiDetail]:
        pois: list[PoiDetail] = []
        sqlite_pois: dict[str, PoiDetail] | None = None
        for poi_id in poi_ids:
            if poi_id in self._seed_pois:
                pois.append(self._seed_pois[poi_id])
                continue
            if sqlite_pois is None:
                sqlite_pois = self._sqlite_pois or {}
            if poi_id in sqlite_pois:
                pois.append(sqlite_pois[poi_id])
                continue
            poi = load_sqlite_poi(self._sqlite_path, poi_id)
            if poi is not None:
                pois.append(poi)
        return pois

    def find_replacement(
        self,
        *,
        exclude_ids: set[str],
        category_hint: Optional[str],
        avoid_queue: bool = True,
        city: str | None = None,
    ) -> Optional[PoiDetail]:
        if city:
            candidates = [poi for poi in self.list_by_city(city, limit=500) if poi.id not in exclude_ids]
        else:
            candidates = [
                poi
                for poi in [*self._seed_pois.values(), *self._load_sqlite_pois().values()]
                if poi.id not in exclude_ids
            ]
        if category_hint:
            same_category = [poi for poi in candidates if poi.category == category_hint]
            if same_category:
                candidates = same_category
        if avoid_queue:
            candidates.sort(key=lambda poi: (poi.queue_estimate["weekend_peak"], -poi.rating))
        else:
            candidates.sort(key=lambda poi: (-poi.rating, poi.queue_estimate["weekend_peak"]))
        return candidates[0] if candidates else None

    def _load_sqlite_pois(self) -> dict[str, PoiDetail]:
        if self._sqlite_pois is None:
            self._sqlite_pois = {poi.id: poi for poi in load_sqlite_pois(self._sqlite_path, "hefei")}
        return self._sqlite_pois

    def _default_sqlite_path(self) -> Path:
        configured = Path(get_settings().poi_sqlite_path)
        if configured.is_absolute():
            return configured
        project_root = Path(__file__).resolve().parents[3]
        return project_root / configured


@lru_cache
def get_poi_repository() -> PoiRepository:
    return PoiRepository()
