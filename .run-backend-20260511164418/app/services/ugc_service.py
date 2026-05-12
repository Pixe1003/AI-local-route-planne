from __future__ import annotations
from app.repositories.poi_repo import get_poi_repository
from app.schemas.plan import UgcSnippet


class UgcService:
    def get_highlight_quotes(
        self, poi_id: str, intent_keywords: list[str], max_count: int = 2
    ) -> list[UgcSnippet]:
        poi = get_poi_repository().get(poi_id)
        quotes = poi.highlight_quotes[:max_count]
        return [
            UgcSnippet(
                quote=quote.quote,
                source=quote.source,
                date=quote.review_date.isoformat() if quote.review_date else None,
            )
            for quote in quotes
        ]

    def estimate_queue(self, poi_id: str, target_datetime: object | None = None) -> int:
        poi = get_poi_repository().get(poi_id)
        return poi.queue_estimate["weekend_peak"]

    def search_similar_pois(
        self, reference_poi_id: str, query_text: str | None, top_k: int = 5
    ) -> list[tuple[str, float]]:
        repo = get_poi_repository()
        reference = repo.get(reference_poi_id)
        candidates = [
            poi for poi in repo.list_by_city(reference.city) if poi.id != reference_poi_id
        ]
        candidates.sort(
            key=lambda poi: (
                poi.category != reference.category,
                poi.queue_estimate["weekend_peak"],
                -poi.rating,
            )
        )
        return [(poi.id, 1.0 - idx * 0.08) for idx, poi in enumerate(candidates[:top_k])]

