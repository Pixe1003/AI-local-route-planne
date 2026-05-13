import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.schemas.ugc import UgcReview, UgcSearchHit


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class UgcVectorRepo:
    """Local UGC evidence index with the same boundary as a vector store adapter."""

    def __init__(self, data_path: str | Path | None = None) -> None:
        self.data_path = _resolve_data_path(data_path)
        self._reviews: list[UgcReview] | None = None

    def list_reviews(self, *, city: str | None = None, limit: int | None = None) -> list[UgcReview]:
        reviews = self._load_reviews()
        if city:
            reviews = [review for review in reviews if review.city == city]
        return reviews[:limit] if limit is not None else reviews

    def has_data(self) -> bool:
        return bool(self._load_reviews())

    def search(
        self,
        query: str,
        *,
        city: str | None = "hefei",
        poi_id: str | None = None,
        top_k: int = 8,
    ) -> list[UgcSearchHit]:
        candidates = self.list_reviews(city=city)
        if poi_id:
            candidates = [review for review in candidates if review.poi_id == poi_id]
        scored = [
            (self._score_review(review, query), review)
            for review in candidates
            if review.content.strip()
        ]
        if query:
            scored = [item for item in scored if item[0] > 0]
        scored.sort(key=lambda item: (item[0], item[1].rating or item[1].poi_rating or 0), reverse=True)
        return [self._to_hit(review, score) for score, review in scored[:top_k]]

    def neighbors_for_poi(self, poi_id: str, *, top_k: int = 6) -> list[UgcSearchHit]:
        return self.search("", poi_id=poi_id, top_k=top_k)

    def evidence_for_poi(self, poi_id: str, query: str | None, *, top_k: int = 3) -> list[UgcSearchHit]:
        hits = self.search(query or "", poi_id=poi_id, top_k=top_k)
        if hits:
            return hits
        return self.neighbors_for_poi(poi_id, top_k=top_k)

    def _load_reviews(self) -> list[UgcReview]:
        if self._reviews is not None:
            return self._reviews
        if not self.data_path.exists():
            self._reviews = []
            return self._reviews

        reviews: list[UgcReview] = []
        with self.data_path.open("r", encoding="utf-8") as file:
            for line_no, line in enumerate(file, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                reviews.extend(_row_to_reviews(row, line_no=line_no))
        self._reviews = reviews
        return self._reviews

    def _score_review(self, review: UgcReview, query: str) -> float:
        if not query:
            return (review.rating or review.poi_rating or 4.0) / 5
        query_tokens = _tokens(query)
        document = " ".join(
            [
                review.poi_name,
                review.content,
                review.category,
                review.sub_category or "",
                review.district or "",
                " ".join(review.tags),
            ]
        )
        document_tokens = _tokens(document)
        overlap = query_tokens & document_tokens
        score = float(len(overlap) * 2)
        query_lc = query.lower()
        document_lc = document.lower()
        for token in query_tokens:
            if len(token) >= 2 and token in document_lc:
                score += 1.5
        if review.poi_name and review.poi_name.lower() in query_lc:
            score += 4
        if score <= 0:
            return 0.0
        score += ((review.rating or review.poi_rating or 4.0) / 5) * 0.5
        return round(score, 4)

    def _to_hit(self, review: UgcReview, score: float) -> UgcSearchHit:
        return UgcSearchHit(
            post_id=review.post_id,
            poi_id=review.poi_id,
            poi_name=review.poi_name,
            snippet=_snippet(review.content),
            source=review.source,
            score=round(score, 4),
            rating=review.rating or review.poi_rating,
            category=review.category,
            tags=review.tags,
        )


@lru_cache
def get_ugc_vector_repo() -> UgcVectorRepo:
    return UgcVectorRepo()


def _resolve_data_path(data_path: str | Path | None) -> Path:
    raw = Path(data_path or get_settings().ugc_reviews_path)
    return raw if raw.is_absolute() else PROJECT_ROOT / raw


def _row_to_reviews(row: dict[str, Any], *, line_no: int) -> list[UgcReview]:
    poi_id = str(row.get("poi_id") or row.get("id") or f"ugc_poi_{line_no:06d}")
    poi_name = str(row.get("poi_name") or row.get("name") or poi_id)
    sub_category = _optional_str(row.get("sub_category") or row.get("category_name"))
    category = str(row.get("category") or _category_from_subcategory(sub_category))
    district = _optional_str(row.get("district"))
    city = str(row.get("city") or "hefei")
    source = str(row.get("source") or "simulated_ugc")
    tags = _tags(category, sub_category, district, row.get("tags"))
    nested_reviews = row.get("reviews")

    if isinstance(nested_reviews, list):
        reviews: list[UgcReview] = []
        for index, item in enumerate(nested_reviews, start=1):
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or item.get("text") or "").strip()
            if not content:
                continue
            reviews.append(
                UgcReview(
                    post_id=str(item.get("post_id") or f"ugc_{poi_id}_{index:03d}"),
                    poi_id=poi_id,
                    poi_name=poi_name,
                    content=content,
                    rating=_float_or_none(item.get("rating")),
                    poi_rating=_float_or_none(row.get("poi_rating") or row.get("rating")),
                    price_per_person=_int_or_none(row.get("price_per_person")),
                    category=category,
                    sub_category=sub_category,
                    district=district,
                    city=city,
                    source=source,
                    author=_optional_str(item.get("author")) or f"ugc_user_{line_no:04d}_{index:02d}",
                    tags=tags,
                )
            )
        return reviews

    content = str(row.get("content") or row.get("text") or row.get("quote") or "").strip()
    if not content:
        return []
    return [
        UgcReview(
            post_id=str(row.get("post_id") or f"ugc_{poi_id}_{line_no:03d}"),
            poi_id=poi_id,
            poi_name=poi_name,
            content=content,
            rating=_float_or_none(row.get("rating")),
            poi_rating=_float_or_none(row.get("poi_rating")),
            price_per_person=_int_or_none(row.get("price_per_person")),
            category=category,
            sub_category=sub_category,
            district=district,
            city=city,
            source=source,
            author=_optional_str(row.get("author")) or f"ugc_user_{line_no:04d}",
            tags=tags,
        )
    ]


def _tokens(text: str) -> set[str]:
    lowered = text.lower()
    tokens = set(re.findall(r"[a-z0-9]+", lowered))
    for sequence in re.findall(r"[\u4e00-\u9fff]+", text):
        tokens.add(sequence)
        for size in (2, 3):
            for index in range(0, max(len(sequence) - size + 1, 0)):
                tokens.add(sequence[index : index + size])
    return {token for token in tokens if token}


def _category_from_subcategory(sub_category: str | None) -> str:
    text = (sub_category or "").lower()
    if any(keyword in text for keyword in ["coffee", "cafe", "咖啡", "茶"]):
        return "cafe"
    if any(keyword in text for keyword in ["景区", "公园", "风景", "trail", "park"]):
        return "scenic"
    if any(keyword in text for keyword in ["博物馆", "展", "艺术", "文化", "museum"]):
        return "culture"
    if any(keyword in text for keyword in ["商场", "购物", "mall", "shop"]):
        return "shopping"
    if any(keyword in text for keyword in ["酒吧", "夜", "bar"]):
        return "nightlife"
    if any(keyword in text for keyword in ["ktv", "影院", "剧本", "娱乐"]):
        return "entertainment"
    return "restaurant"


def _tags(
    category: str,
    sub_category: str | None,
    district: str | None,
    raw_tags: Any,
) -> list[str]:
    values: list[str] = []
    if isinstance(raw_tags, list):
        values.extend(str(item) for item in raw_tags if item)
    values.extend(item for item in [sub_category, district, category] if item)
    return list(dict.fromkeys(values))


def _snippet(content: str, limit: int = 120) -> str:
    content = " ".join(content.split())
    return content if len(content) <= limit else f"{content[:limit]}..."


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
