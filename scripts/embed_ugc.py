import json
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer


MODEL_NAME = "BAAI/bge-small-zh-v1.5"
DATA_PATH = Path("data/processed/ugc_hefei.jsonl")
FAISS_INDEX_PATH = Path("data/processed/ugc_hefei.faiss")
EMBED_PATH = Path("data/processed/ugc_hefei_embeddings.npy")
META_PATH = Path("data/processed/ugc_hefei_meta.jsonl")


def main() -> None:
    model = SentenceTransformer(MODEL_NAME)
    texts: list[str] = []
    metas: list[dict] = []

    with DATA_PATH.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            row = json.loads(line)
            for review in row.get("reviews", []):
                content = (review.get("content") or "").strip()
                if not content:
                    continue
                texts.append(content)
                metas.append(
                    {
                        "poi_id": row["poi_id"],
                        "poi_name": row.get("poi_name"),
                        "category": row.get("category"),
                        "sub_category": row.get("sub_category"),
                        "district": row.get("district"),
                        "city": row.get("city", "hefei"),
                        "rating": review.get("rating"),
                        "content": content,
                        "source": row.get("source", "simulated_ugc"),
                        "tags": row.get("tags", []),
                        "post_id": review.get("post_id") or f"ugc_{row['poi_id']}_{len(texts):05d}",
                    }
                )

    print(f"Encoding {len(texts)} reviews with {MODEL_NAME}...")
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=True,
        batch_size=32,
    )
    embeddings = np.ascontiguousarray(embeddings.astype("float32"))
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)
    EMBED_PATH.parent.mkdir(parents=True, exist_ok=True)
    FAISS_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    META_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.save(EMBED_PATH, embeddings)
    faiss.write_index(index, str(FAISS_INDEX_PATH))
    with META_PATH.open("w", encoding="utf-8") as file:
        for meta in metas:
            file.write(json.dumps(meta, ensure_ascii=False) + "\n")
    print(f"Saved FAISS index with {index.ntotal} vectors to {FAISS_INDEX_PATH}")
    print(f"Saved {len(embeddings)} embeddings to {EMBED_PATH}")
    print(f"Saved metadata to {META_PATH}")


if __name__ == "__main__":
    main()
