from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import get_settings
from app.llm.embedding import Embedder, SentenceTransformerEmbedder
from app.repositories.poi_repo import DEFAULT_POI_DB_PATH, PoiRepository
from app.repositories.rag_build import documents_for_pois, write_faiss_index
from app.repositories.sqlite_poi_repo import load_sqlite_pois


def build_faiss_rag(
    *,
    city: str | None,
    index_dir: Path,
    sqlite_path: Path | None = None,
    require_real_data: bool = False,
    limit: int | None = None,
    embedder: Embedder | None = None,
) -> dict[str, int]:
    target_city = city or get_settings().default_city
    db_path = sqlite_path or DEFAULT_POI_DB_PATH
    real_rows = load_sqlite_pois(db_path, city=target_city, limit=1)
    if require_real_data and not real_rows:
        raise FileNotFoundError(
            f"real SQLite POI data is required but not available at {db_path}"
        )

    repo = PoiRepository(sqlite_path=db_path)
    pois = repo.list_by_city(target_city, limit=limit)
    documents = documents_for_pois(pois)
    stats = write_faiss_index(
        documents,
        index_dir,
        embedder=embedder or SentenceTransformerEmbedder(),
    )
    return {"pois": len(pois), "real_sqlite_rows": len(real_rows), **stats}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build unified POI/UGC FAISS RAG index.")
    parser.add_argument("--city", default="hefei")
    parser.add_argument("--index-dir", type=Path, default=Path("data/faiss"))
    parser.add_argument("--sqlite-path", type=Path, default=None)
    parser.add_argument("--require-real-data", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    stats = build_faiss_rag(
        city=args.city,
        index_dir=args.index_dir,
        sqlite_path=args.sqlite_path,
        require_real_data=args.require_real_data,
        limit=args.limit,
    )
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
