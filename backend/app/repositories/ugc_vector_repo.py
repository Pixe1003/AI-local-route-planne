import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.schemas.ugc import UgcReview, UgcSearchHit


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODEL_NAME = "BAAI/bge-small-zh-v1.5"
SentenceTransformer = None


class UgcVectorRepo:
    """Local UGC evidence index with the same boundary as a vector store adapter."""

    def __init__(
        self,
        data_path: str | Path | None = None,
        *,
        faiss_index_path: str | Path | None = None,
        embed_path: str | Path | None = None,
        meta_path: str | Path | None = None,
    ) -> None:
        self.data_path = _resolve_data_path(data_path)
        self._faiss_index_path = _resolve_optional_path(
            faiss_index_path,
            PROJECT_ROOT / "data" / "processed" / "ugc_hefei.faiss",
        )
        self._embed_path = _resolve_optional_path(
            embed_path,
            PROJECT_ROOT / "data" / "processed" / "ugc_hefei_embeddings.npy",
        )
        self._meta_path = _resolve_optional_path(
            meta_path,
            PROJECT_ROOT / "data" / "processed" / "ugc_hefei_meta.jsonl",
        )
        self._reviews: list[UgcReview] | None = None
        self._faiss_index: Any | None = None
        self._embeddings: Any | None = None
        self._metas: list[dict[str, Any]] | None = None
        self._model: Any | None = None

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
        if query and self._ensure_faiss_index():
            return self._search_faiss(query, city=city, poi_id=poi_id, top_k=top_k)
        if query and self._ensure_embeddings():
            return self._search_semantic(query, city=city, poi_id=poi_id, top_k=top_k)
        return self._search_lexical(query, city=city, poi_id=poi_id, top_k=top_k)

    def _search_lexical(
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

    def _ensure_faiss_index(self) -> bool:
        if self._faiss_index is not None and self._metas is not None and self._model is not None:
            return True
        if not (self._faiss_index_path.exists() and self._meta_path.exists()):
            return False
        try:
            import faiss
        except ImportError:
            return False
        model_cls = self._load_model_cls()
        if model_cls is None:
            return False

        try:
            index = faiss.read_index(str(self._faiss_index_path))
            metas = self._load_metas()
            model = model_cls(MODEL_NAME)
        except Exception:
            return False
        if len(metas) != int(index.ntotal):
            return False
        self._faiss_index = index
        self._metas = metas
        self._model = model
        return True

    def _ensure_embeddings(self) -> bool:
        if self._embeddings is not None and self._metas is not None and self._model is not None:
            return True
        if not (self._embed_path.exists() and self._meta_path.exists()):
            return False
        try:
            import numpy as np
        except ImportError:
            return False
        model_cls = self._load_model_cls()
        if model_cls is None:
            return False

        try:
            self._embeddings = np.load(self._embed_path)
            self._metas = self._load_metas()
            model = model_cls(MODEL_NAME)
        except Exception:
            self._embeddings = None
            self._metas = None
            return False
        if len(self._metas) != len(self._embeddings):
            self._embeddings = None
            self._metas = None
            return False
        self._model = model
        return True

    def _load_model_cls(self) -> Any | None:
        model_cls = SentenceTransformer
        if model_cls is not None:
            return model_cls
        try:
            from sentence_transformers import SentenceTransformer as model_cls
        except ImportError:
            return None
        return model_cls

    def _load_metas(self) -> list[dict[str, Any]]:
        return [
            json.loads(line)
            for line in self._meta_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def _search_faiss(
        self,
        query: str,
        *,
        city: str | None,
        poi_id: str | None,
        top_k: int,
    ) -> list[UgcSearchHit]:
        import numpy as np

        assert self._faiss_index is not None
        assert self._metas is not None
        assert self._model is not None

        q_emb = np.asarray(
            self._model.encode(query, normalize_embeddings=True),
            dtype="float32",
        )
        if q_emb.ndim == 1:
            q_emb = q_emb.reshape(1, -1)
        search_k = top_k
        if poi_id:
            search_k = int(self._faiss_index.ntotal)
        elif city:
            search_k = min(int(self._faiss_index.ntotal), max(top_k * 4, top_k))
        scores, indices = self._faiss_index.search(q_emb, search_k)
        hits: list[UgcSearchHit] = []
        for score, index in zip(scores[0], indices[0]):
            index = int(index)
            if index < 0 or index >= len(self._metas):
                continue
            meta = self._metas[index]
            if city and meta.get("city", city) != city:
                continue
            if poi_id and meta.get("poi_id") != poi_id:
                continue
            hits.append(self._meta_to_hit(meta, float(score)))
            if len(hits) >= top_k:
                break
        return hits

    def _search_semantic(
        self,
        query: str,
        *,
        city: str | None,
        poi_id: str | None,
        top_k: int,
    ) -> list[UgcSearchHit]:
        import numpy as np

        assert self._embeddings is not None
        assert self._metas is not None
        assert self._model is not None

        q_emb = self._model.encode(query, normalize_embeddings=True).astype("float32")
        scores = self._embeddings @ q_emb
        mask = np.ones(len(scores), dtype=bool)
        if city:
            mask = np.array(
                [meta.get("city", city) == city for meta in self._metas],
                dtype=bool,
            )
        if poi_id:
            poi_mask = np.array([meta.get("poi_id") == poi_id for meta in self._metas], dtype=bool)
            mask = mask & poi_mask
        scores = np.where(mask, scores, -1.0)
        top_idx = np.argsort(-scores)[:top_k]
        return [
            self._meta_to_hit(self._metas[index], float(scores[index]))
            for index in top_idx
            if mask[index]
        ]

    def _meta_to_hit(self, meta: dict[str, Any], score: float) -> UgcSearchHit:
        category = str(meta.get("category") or _category_from_subcategory(_optional_str(meta.get("sub_category"))))
        content = str(meta.get("content") or "")
        return UgcSearchHit(
            post_id=str(meta.get("post_id") or f"ugc_{meta.get('poi_id', 'unknown')}"),
            poi_id=str(meta.get("poi_id") or ""),
            poi_name=str(meta.get("poi_name") or meta.get("poi_id") or ""),
            snippet=_snippet(content),
            source=str(meta.get("source") or "simulated_ugc"),
            score=round(score, 4),
            rating=_float_or_none(meta.get("rating")),
            category=category,
            tags=[str(item) for item in meta.get("tags", [])] if isinstance(meta.get("tags"), list) else [],
        )

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


def _resolve_optional_path(path: str | Path | None, default: Path) -> Path:
    if path is None:
        return default
    raw = Path(path)
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
