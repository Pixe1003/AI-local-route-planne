from app.config import get_settings
from app.llm.embedding import EmbeddingUnavailable
from app.repositories.faiss_index import FaissVectorIndex
from app.repositories.poi_repo import PoiRepository, get_poi_repository
from app.schemas.rag import EvidenceSnippet, RetrievalQuery, RetrievedPoi
from app.services.category_policy import categories_for_groups
from app.services.location_context import origin_from_query, within_radius


_UNSET = object()
PROVENANCE_BY_SOURCE = {
    "poi_profile": "semantic_poi_profile",
    "ugc_review": "semantic_ugc_review",
    "fts": "fts",
    "feature_bucket": "feature_bucket",
}


class RetrievalService:
    def __init__(self, repo: PoiRepository | None = None, vector_index=_UNSET) -> None:
        self.repo = repo or get_poi_repository()
        self.vector_index = self._default_vector_index() if vector_index is _UNSET else vector_index

    def retrieve(self, query: RetrievalQuery) -> list[RetrievedPoi]:
        if self.vector_index is None:
            return []
        text = self._query_text(query)
        if not text:
            return []
        try:
            rows = self._query_vector_index(text, query)
        except (EmbeddingUnavailable, FileNotFoundError):
            return []
        except Exception:
            return []

        grouped = self._group_rows_by_poi(rows)
        origin = origin_from_query(query)
        results: list[RetrievedPoi] = []
        for poi_id, group in sorted(grouped.items(), key=lambda item: item[1]["score"], reverse=True):
            try:
                poi = self.repo.get(poi_id)
            except KeyError:
                continue
            if poi.city != query.city:
                continue
            if query.budget_per_person and poi.price_per_person:
                if poi.price_per_person > query.budget_per_person * 1.5:
                    continue
            if query.avoid_queue and poi.queue_estimate.get("weekend_peak", 0) > 50:
                continue
            if not within_radius(poi, origin, query.radius_meters):
                continue
            results.append(
                RetrievedPoi(
                    poi_id=poi_id,
                    score=round(float(group["score"] or 0.0), 4),
                    evidence_snippets=group["evidence"][:3],
                    provenance=self._provenance(group["source_types"]),
                )
            )
            if len(results) >= query.top_k:
                break
        return results

    def _query_text(self, query: RetrievalQuery) -> str:
        parts = [query.text or "", *query.preference_terms]
        return " ".join(part.strip() for part in parts if part and part.strip())

    def _query_vector_index(self, text: str, query: RetrievalQuery):
        return self.vector_index.query(
            text=text,
            city=query.city,
            top_k=max(query.top_k * 4, query.top_k),
            category_filters=self._category_filters(query),
            source_types=query.source_types or None,
        )

    def _category_filters(self, query: RetrievalQuery) -> list[str]:
        categories = list(query.category_filters)
        categories.extend(categories_for_groups(query.category_groups))
        return list(dict.fromkeys(categories))

    def _group_rows_by_poi(self, rows) -> dict[str, dict]:
        grouped: dict[str, dict] = {}
        for row in rows:
            poi_id = str(row.get("poi_id") or "")
            if not poi_id:
                continue
            score = float(row.get("score") or 0.0)
            source_type = str(row.get("source_type") or "poi_profile")
            group = grouped.setdefault(
                poi_id,
                {"score": 0.0, "evidence": [], "source_types": set()},
            )
            group["score"] = max(float(group["score"]), score)
            group["source_types"].add(source_type)
            group["evidence"].append(
                EvidenceSnippet(
                    doc_id=str(row.get("doc_id") or f"{source_type}:{poi_id}"),
                    source_type=source_type,
                    text=str(row.get("text") or ""),
                    score=round(score, 4),
                )
            )
        for group in grouped.values():
            group["evidence"].sort(key=lambda item: item.score, reverse=True)
        return grouped

    def _provenance(self, source_types: set[str]) -> list[str]:
        ordered = ["poi_profile", "ugc_review", "fts", "feature_bucket"]
        provenance = [
            PROVENANCE_BY_SOURCE[source_type]
            for source_type in ordered
            if source_type in source_types and source_type in PROVENANCE_BY_SOURCE
        ]
        for source_type in sorted(source_types - set(ordered)):
            provenance.append(f"semantic_{source_type}")
        return provenance

    def _default_vector_index(self):
        settings = get_settings()
        if not settings.rag_enabled:
            return None
        index = FaissVectorIndex(path=settings.faiss_index_path)
        return index if index.exists() else None
