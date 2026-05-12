from functools import lru_cache
from typing import Iterable, Optional

from app.repositories.seed_data import load_seed_pois
from app.schemas.poi import PoiDetail


class PoiRepository:
    def __init__(self) -> None:
        self._pois = {poi.id: poi for poi in load_seed_pois()}

    def list_by_city(self, city: str) -> list[PoiDetail]:
        return [poi for poi in self._pois.values() if poi.city == city]

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
