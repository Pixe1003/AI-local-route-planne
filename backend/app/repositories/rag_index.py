import argparse
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.llm.embedding import EmbeddingClient, EmbeddingUnavailable
from app.repositories.poi_repo import PoiRepository
from app.schemas.poi import PoiDetail
from app.schemas.rag import RagDocument


COLLECTION_NAME = "poi_profiles"


def build_poi_document(poi: PoiDetail) -> RagDocument:
    keyword_text = "、".join(
        str(item.get("keyword", "")) for item in poi.high_freq_keywords[:8] if item.get("keyword")
    )
    tags = "、".join(item for item in poi.tags if item)
    suitable_for = "、".join(poi.suitable_for)
    atmosphere = "、".join(poi.atmosphere)
    evidence = poi.highlight_quotes[0].quote if poi.highlight_quotes else ""
    text = "\n".join(
        item
        for item in [
            f"名称：{poi.name}",
            f"城市：{poi.city}",
            f"类别：{poi.category}",
            f"子类：{poi.sub_category or ''}",
            f"地址：{poi.address}",
            f"标签：{tags}",
            f"适合人群：{suitable_for}",
            f"氛围：{atmosphere}",
            f"高频关键词：{keyword_text}",
            f"证据摘要：{evidence}",
        ]
        if item
    )
    return RagDocument(
        doc_id=f"poi_profile:{poi.id}",
        poi_id=poi.id,
        text=text,
        metadata={
            "poi_id": poi.id,
            "city": poi.city,
            "category": poi.category,
            "sub_category": poi.sub_category or "",
            "district": _district_from_poi(poi),
            "business_area": _business_area_from_poi(poi),
            "source_type": "poi_profile",
            "rating": float(poi.rating or 0.0),
            "price_per_person": poi.price_per_person if poi.price_per_person is not None else -1,
            "queue_weekend_peak": poi.queue_estimate.get("weekend_peak", 0),
        },
    )


def build_ugc_documents(poi: PoiDetail) -> list[RagDocument]:
    documents: list[RagDocument] = []
    for index, quote in enumerate(poi.highlight_quotes):
        text = quote.quote.strip()
        if not text or quote.source == "poi_profile" or quote.category == "poi_profile":
            continue
        documents.append(
            RagDocument(
                doc_id=f"ugc_review:{poi.id}:{index}",
                poi_id=poi.id,
                text=text,
                metadata={
                    "poi_id": poi.id,
                    "city": poi.city,
                    "category": poi.category,
                    "sub_category": poi.sub_category or "",
                    "district": _district_from_poi(poi),
                    "business_area": _business_area_from_poi(poi),
                    "source_type": "ugc_review",
                    "rating": float(poi.rating or 0.0),
                    "price_per_person": poi.price_per_person if poi.price_per_person is not None else -1,
                    "queue_weekend_peak": poi.queue_estimate.get("weekend_peak", 0),
                    "quote_source": quote.source,
                    "quote_category": quote.category,
                },
            )
        )
    return documents


def _district_from_poi(poi: PoiDetail) -> str:
    for tag in poi.tags:
        if tag and (tag.endswith("区") or tag.endswith("县") or tag.endswith("市")):
            return tag
    return ""


def _business_area_from_poi(poi: PoiDetail) -> str:
    district = _district_from_poi(poi)
    for tag in poi.tags:
        if tag and tag != district and not tag.startswith("hefei") and len(tag) <= 12:
            if not any(keyword in tag for keyword in ["餐饮", "景点", "购物", "风景名胜"]):
                return tag
    return ""


class ChromaVectorIndex:
    def __init__(
        self,
        *,
        path: str | Path | None = None,
        embedding_client: EmbeddingClient | None = None,
        collection_name: str = COLLECTION_NAME,
    ) -> None:
        self.path = Path(path or get_settings().vector_db_path)
        self.embedding_client = embedding_client or EmbeddingClient()
        self.collection_name = collection_name
        self._collection = None

    def upsert_pois(self, pois: list[PoiDetail], *, reset: bool = False, batch_size: int = 128) -> int:
        collection = self._get_collection(reset=reset)
        documents = []
        for poi in pois:
            documents.append(build_poi_document(poi))
            documents.extend(build_ugc_documents(poi))
        for start in range(0, len(documents), batch_size):
            batch = documents[start : start + batch_size]
            embeddings = self.embedding_client.embed_texts([doc.text for doc in batch])
            collection.upsert(
                ids=[doc.doc_id for doc in batch],
                documents=[doc.text for doc in batch],
                metadatas=[doc.metadata for doc in batch],
                embeddings=embeddings,
            )
        return len(documents)

    def query(
        self,
        *,
        text: str,
        city: str,
        top_k: int,
        category_filters: list[str] | None = None,
        source_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not text.strip():
            return []
        collection = self._get_collection(reset=False)
        if hasattr(self.embedding_client, "embed_query"):
            embedding = self.embedding_client.embed_query(text)
        else:
            embedding = self.embedding_client.embed_texts([text])[0]
        where = _query_where(
            city=city,
            source_types=source_types,
            category_filters=category_filters,
        )
        result = collection.query(
            query_embeddings=[embedding],
            n_results=max(top_k * 4, top_k),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        rows: list[dict[str, Any]] = []
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        for doc_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
            rows.append(
                {
                    "poi_id": metadata.get("poi_id"),
                    "score": max(0.0, 1.0 - float(distance or 0.0)),
                    "doc_id": doc_id,
                    "source_type": metadata.get("source_type", "poi_profile"),
                    "text": document,
                    "metadata": metadata,
                }
            )
            if len(rows) >= top_k:
                break
        return rows

    def _get_collection(self, *, reset: bool):
        try:
            import chromadb
        except Exception as exc:  # pragma: no cover - depends on optional runtime package
            raise EmbeddingUnavailable("chromadb is not installed") from exc
        self.path.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(self.path))
        if reset:
            try:
                client.delete_collection(self.collection_name)
            except Exception:
                pass
            self._collection = None
        if self._collection is None:
            self._collection = client.get_or_create_collection(
                self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection


def _query_where(
    *,
    city: str,
    source_types: list[str] | None = None,
    category_filters: list[str] | None = None,
) -> dict[str, Any]:
    clauses: list[dict[str, Any]] = [{"city": city}]
    if source_types:
        clauses.append({"source_type": {"$in": list(dict.fromkeys(source_types))}})
    if category_filters:
        clauses.append({"category": {"$in": list(dict.fromkeys(category_filters))}})
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def get_rag_status(path: str | Path | None = None, collection_name: str = COLLECTION_NAME) -> dict[str, Any]:
    settings = get_settings()
    db_path = Path(path or settings.vector_db_path)
    status: dict[str, Any] = {
        "enabled": settings.rag_enabled,
        "index_exists": db_path.exists(),
        "collection_count": 0,
        "embedding_configured": bool(settings.embedding_api_key),
    }
    if not db_path.exists():
        return status
    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(db_path))
        collection = client.get_collection(collection_name)
        status["collection_count"] = int(collection.count())
    except Exception:
        status["collection_count"] = 0
    return status


def build_index(*, city: str, source: str | Path, reset: bool = False) -> int:
    repo = PoiRepository(sqlite_path=source)
    pois = repo.list_by_city(city)
    return ChromaVectorIndex().upsert_pois(pois, reset=reset)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.repositories.rag_index")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--city", default=get_settings().default_city)
    build_parser.add_argument("--source", default=get_settings().poi_sqlite_path)
    build_parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    if args.command == "build":
        count = build_index(city=args.city, source=args.source, reset=args.reset)
        print(f"indexed_poi_documents={count}")


if __name__ == "__main__":
    main()
