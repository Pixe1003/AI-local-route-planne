from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import get_settings
from app.llm.embedding import SentenceTransformerEmbedder
from app.repositories.poi_repo import PoiRepository
from app.repositories.rag_build import documents_for_pois, write_faiss_index


def build_faiss_rag(*, city: str | None, index_dir: Path) -> dict[str, int]:
    repo = PoiRepository()
    pois = repo.list_by_city(city or get_settings().default_city, limit=None)
    documents = documents_for_pois(pois)
    stats = write_faiss_index(documents, index_dir, embedder=SentenceTransformerEmbedder())
    return {"pois": len(pois), **stats}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build unified POI/UGC FAISS RAG index.")
    parser.add_argument("--city", default="hefei")
    parser.add_argument("--index-dir", type=Path, default=Path("data/faiss"))
    args = parser.parse_args()

    stats = build_faiss_rag(city=args.city, index_dir=args.index_dir)
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
