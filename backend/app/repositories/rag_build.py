from pathlib import Path
from typing import Iterable

import numpy as np

from app.llm.embedding import Embedder
from app.repositories.faiss_meta import FaissMetaStore
from app.schemas.poi import HighlightQuote, PoiDetail
from app.schemas.rag import RagDocument


INDEX_FILENAME = "index.faiss"
META_FILENAME = "meta.jsonl"


def build_poi_document(poi: PoiDetail) -> RagDocument:
    keyword_text = " ".join(
        str(item.get("keyword", "")) for item in poi.high_freq_keywords[:8] if item.get("keyword")
    )
    quote_text = " ".join(quote.quote for quote in poi.highlight_quotes[:3])
    text = " ".join(
        item
        for item in [
            "profile",
            poi.name,
            poi.category,
            poi.sub_category or "",
            poi.district or "",
            poi.address,
            " ".join(poi.tags),
            keyword_text,
            quote_text,
        ]
        if item
    )
    return RagDocument(
        doc_id=f"poi_profile:{poi.id}",
        poi_id=poi.id,
        text=text,
        metadata=_base_metadata(poi, "poi_profile"),
    )


def build_ugc_documents(poi: PoiDetail) -> list[RagDocument]:
    documents: list[RagDocument] = []
    for index, quote in enumerate(_ugc_quotes(poi)):
        text = " ".join(
            item
            for item in [
                "review",
                poi.name,
                poi.category,
                poi.sub_category or "",
                poi.district or "",
                quote.quote,
            ]
            if item
        )
        metadata = _base_metadata(poi, "ugc_review")
        metadata.update({"source": quote.source, "review_rank": index})
        documents.append(
            RagDocument(
                doc_id=f"ugc_review:{poi.id}:{index}",
                poi_id=poi.id,
                text=text,
                metadata=metadata,
            )
        )
    return documents


def documents_for_pois(pois: Iterable[PoiDetail]) -> list[RagDocument]:
    documents: list[RagDocument] = []
    for poi in pois:
        documents.append(build_poi_document(poi))
        documents.extend(build_ugc_documents(poi))
    return documents


def write_faiss_index(
    documents: list[RagDocument],
    index_dir: str | Path,
    *,
    embedder: Embedder,
) -> dict[str, int]:
    index_path, meta_path = resolve_faiss_paths(index_dir)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    if not documents:
        FaissMetaStore(meta_path).write([])
        return {"documents": 0, "dimensions": 0}

    embeddings = np.asarray(embedder.embed_documents([doc.text for doc in documents]), dtype="float32")
    if embeddings.ndim != 2 or embeddings.shape[0] != len(documents):
        raise ValueError("embedder returned an invalid embedding matrix")
    embeddings = _normalize_rows(embeddings)

    import faiss

    index = faiss.IndexFlatIP(int(embeddings.shape[1]))
    index.add(embeddings)
    faiss.write_index(index, str(index_path))
    FaissMetaStore(meta_path).write([_meta_row(doc, idx) for idx, doc in enumerate(documents)])
    return {"documents": len(documents), "dimensions": int(embeddings.shape[1])}


def resolve_faiss_paths(index_dir: str | Path) -> tuple[Path, Path]:
    path = Path(index_dir)
    if path.suffix == ".faiss":
        return path, path.with_suffix(".meta.jsonl")
    return path / INDEX_FILENAME, path / META_FILENAME


def _base_metadata(poi: PoiDetail, source_type: str) -> dict:
    return {
        "poi_id": poi.id,
        "city": poi.city,
        "category": poi.category,
        "sub_category": poi.sub_category or "",
        "district": poi.district or "",
        "business_area": "",
        "source_type": source_type,
        "price": poi.price_per_person,
        "queue": poi.queue_estimate.get("weekend_peak"),
    }


def _ugc_quotes(poi: PoiDetail) -> list[HighlightQuote]:
    quotes = [quote for quote in poi.highlight_quotes if quote.category == "ugc_review"]
    if quotes:
        return quotes
    return [quote for quote in poi.highlight_quotes if quote.source not in {"poi_profile", "hefei_excel"}]


def _meta_row(document: RagDocument, faiss_id: int) -> dict:
    return {
        "faiss_id": faiss_id,
        "doc_id": document.doc_id,
        "poi_id": document.poi_id,
        "text": document.text,
        "metadata": document.metadata,
        "source_type": document.metadata.get("source_type", "poi_profile"),
        "city": document.metadata.get("city"),
        "category": document.metadata.get("category"),
    }


def _normalize_rows(values: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return values / norms
