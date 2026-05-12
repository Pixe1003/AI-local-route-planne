from app.repositories.poi_repo import get_poi_repository
from app.schemas.preferences import PreferenceSnapshot, PreferenceSnapshotRequest


class PreferenceService:
    def __init__(self) -> None:
        self.repo = get_poi_repository()

    def build_snapshot(self, request: PreferenceSnapshotRequest) -> PreferenceSnapshot:
        city_pois = {poi.id: poi for poi in self.repo.list_by_city(request.city)}
        liked_ids = [poi_id for poi_id in request.liked_poi_ids if poi_id in city_pois]
        disliked_ids = [poi_id for poi_id in request.disliked_poi_ids if poi_id in city_pois]

        category_weights: dict[str, float] = {}
        tag_weights: dict[str, float] = {}
        keyword_weights: dict[str, float] = {}
        for poi_id in liked_ids:
            poi = city_pois[poi_id]
            category_weights[poi.category] = category_weights.get(poi.category, 0.0) + 1.0
            for tag in poi.tags + poi.suitable_for + poi.atmosphere:
                tag_weights[tag] = tag_weights.get(tag, 0.0) + 1.0
            for item in poi.high_freq_keywords:
                keyword = str(item.get("keyword", ""))
                if keyword:
                    keyword_weights[keyword] = keyword_weights.get(keyword, 0.0) + 1.0

        return PreferenceSnapshot(
            user_id=request.user_id,
            liked_poi_ids=liked_ids,
            disliked_poi_ids=disliked_ids,
            tag_weights=self._normalize(tag_weights),
            category_weights=self._normalize(category_weights),
            keyword_weights=self._normalize(keyword_weights),
        )

    def _normalize(self, weights: dict[str, float]) -> dict[str, float]:
        if not weights:
            return {}
        top = max(weights.values()) or 1.0
        return {key: round(value / top, 3) for key, value in sorted(weights.items())}
