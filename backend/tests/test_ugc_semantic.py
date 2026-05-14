import json
import sys
from types import SimpleNamespace

import pytest

from app.repositories.ugc_vector_repo import UgcVectorRepo


np = pytest.importorskip("numpy")


class FakeModel:
    def encode(self, text, normalize_embeddings=True):
        if "quiet" in text or "cafe" in text:
            return np.array([1.0, 0.0], dtype="float32")
        return np.array([0.0, 1.0], dtype="float32")


class FakeFaissIndex:
    ntotal = 2

    def __init__(self) -> None:
        self.search_calls: list[tuple[np.ndarray, int]] = []

    def search(self, vectors, top_k):
        self.search_calls.append((vectors, top_k))
        return (
            np.array([[0.9, 0.2]], dtype="float32"),
            np.array([[0, 1]], dtype="int64"),
        )


class FakeRankedFaissIndex:
    ntotal = 10

    def __init__(self) -> None:
        self.search_calls: list[tuple[np.ndarray, int]] = []

    def search(self, vectors, top_k):
        self.search_calls.append((vectors, top_k))
        indices = np.arange(top_k, dtype="int64").reshape(1, -1)
        scores = np.linspace(1.0, 0.1, top_k, dtype="float32").reshape(1, -1)
        return scores, indices


def _write_meta(path, metas) -> None:
    path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in metas),
        encoding="utf-8",
    )


def test_ugc_vector_repo_uses_semantic_embeddings_when_available(tmp_path, monkeypatch) -> None:
    embed_path = tmp_path / "ugc.npy"
    meta_path = tmp_path / "ugc_meta.jsonl"
    data_path = tmp_path / "ugc.jsonl"
    np.save(embed_path, np.array([[1.0, 0.0], [0.0, 1.0]], dtype="float32"))
    _write_meta(
        meta_path,
        [
            {
                "post_id": "ugc_cafe_001",
                "poi_id": "cafe_1",
                "poi_name": "Quiet Cafe",
                "category": "cafe",
                "sub_category": "cafe",
                "district": "baohe",
                "city": "hefei",
                "rating": 4.8,
                "content": "quiet cafe for working",
                "source": "test",
                "tags": ["cafe"],
            },
            {
                "post_id": "ugc_hotpot_001",
                "poi_id": "hotpot_1",
                "poi_name": "Busy Hotpot",
                "category": "restaurant",
                "sub_category": "hotpot",
                "district": "luyang",
                "city": "hefei",
                "rating": 4.6,
                "content": "busy hotpot for dinner",
                "source": "test",
                "tags": ["hotpot"],
            },
        ],
    )
    data_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        "app.repositories.ugc_vector_repo.SentenceTransformer",
        lambda model_name: FakeModel(),
        raising=False,
    )
    repo = UgcVectorRepo(data_path, embed_path=embed_path, meta_path=meta_path)

    hits = repo.search("quiet cafe", top_k=2)

    assert [hit.poi_id for hit in hits] == ["cafe_1", "hotpot_1"]
    assert hits[0].category == "cafe"
    assert hits[0].score > hits[1].score


def test_ugc_vector_repo_filters_semantic_hits_by_poi_id(tmp_path, monkeypatch) -> None:
    embed_path = tmp_path / "ugc.npy"
    meta_path = tmp_path / "ugc_meta.jsonl"
    data_path = tmp_path / "ugc.jsonl"
    np.save(embed_path, np.array([[1.0, 0.0], [0.0, 1.0]], dtype="float32"))
    _write_meta(
        meta_path,
        [
            {
                "post_id": "ugc_cafe_001",
                "poi_id": "cafe_1",
                "poi_name": "Quiet Cafe",
                "category": "cafe",
                "city": "hefei",
                "content": "quiet cafe",
            },
            {
                "post_id": "ugc_hotpot_001",
                "poi_id": "hotpot_1",
                "poi_name": "Busy Hotpot",
                "category": "restaurant",
                "city": "hefei",
                "content": "busy hotpot",
            },
        ],
    )
    data_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "app.repositories.ugc_vector_repo.SentenceTransformer",
        lambda model_name: FakeModel(),
        raising=False,
    )
    repo = UgcVectorRepo(data_path, embed_path=embed_path, meta_path=meta_path)

    hits = repo.search("quiet cafe", poi_id="hotpot_1", top_k=2)

    assert [hit.poi_id for hit in hits] == ["hotpot_1"]


def test_ugc_vector_repo_uses_faiss_index_when_available(tmp_path, monkeypatch) -> None:
    index_path = tmp_path / "ugc.faiss"
    meta_path = tmp_path / "ugc_meta.jsonl"
    data_path = tmp_path / "ugc.jsonl"
    index_path.write_bytes(b"fake-faiss-index")
    _write_meta(
        meta_path,
        [
            {
                "post_id": "ugc_cafe_001",
                "poi_id": "cafe_1",
                "poi_name": "Quiet Cafe",
                "category": "cafe",
                "city": "hefei",
                "content": "quiet cafe",
            },
            {
                "post_id": "ugc_hotpot_001",
                "poi_id": "hotpot_1",
                "poi_name": "Busy Hotpot",
                "category": "restaurant",
                "city": "hefei",
                "content": "busy hotpot",
            },
        ],
    )
    data_path.write_text("", encoding="utf-8")
    fake_index = FakeFaissIndex()
    monkeypatch.setitem(
        sys.modules,
        "faiss",
        SimpleNamespace(read_index=lambda path: fake_index),
    )
    monkeypatch.setattr(
        "app.repositories.ugc_vector_repo.SentenceTransformer",
        lambda model_name: FakeModel(),
        raising=False,
    )

    repo = UgcVectorRepo(data_path, faiss_index_path=index_path, meta_path=meta_path)
    hits = repo.search("quiet cafe", top_k=2)

    assert [hit.poi_id for hit in hits] == ["cafe_1", "hotpot_1"]
    assert fake_index.search_calls
    query_vectors, requested_top_k = fake_index.search_calls[0]
    assert query_vectors.shape == (1, 2)
    assert requested_top_k == 2


def test_ugc_vector_repo_searches_full_faiss_index_for_poi_filter(tmp_path, monkeypatch) -> None:
    index_path = tmp_path / "ugc.faiss"
    meta_path = tmp_path / "ugc_meta.jsonl"
    data_path = tmp_path / "ugc.jsonl"
    index_path.write_bytes(b"fake-faiss-index")
    metas = [
        {
            "post_id": f"ugc_other_{index}",
            "poi_id": f"other_{index}",
            "poi_name": f"Other {index}",
            "category": "restaurant",
            "city": "hefei",
            "content": f"other review {index}",
        }
        for index in range(9)
    ]
    metas.append(
        {
            "post_id": "ugc_target_001",
            "poi_id": "target_poi",
            "poi_name": "Target Cafe",
            "category": "cafe",
            "city": "hefei",
            "content": "target review",
        }
    )
    _write_meta(meta_path, metas)
    data_path.write_text("", encoding="utf-8")
    fake_index = FakeRankedFaissIndex()
    monkeypatch.setitem(
        sys.modules,
        "faiss",
        SimpleNamespace(read_index=lambda path: fake_index),
    )
    monkeypatch.setattr(
        "app.repositories.ugc_vector_repo.SentenceTransformer",
        lambda model_name: FakeModel(),
        raising=False,
    )

    repo = UgcVectorRepo(data_path, faiss_index_path=index_path, meta_path=meta_path)
    hits = repo.search("quiet cafe", poi_id="target_poi", top_k=1)

    assert [hit.poi_id for hit in hits] == ["target_poi"]
    assert fake_index.search_calls[0][1] == 10


def test_ugc_vector_repo_falls_back_when_faiss_read_fails(tmp_path, monkeypatch) -> None:
    index_path = tmp_path / "ugc.faiss"
    meta_path = tmp_path / "ugc_meta.jsonl"
    data_path = tmp_path / "ugc.jsonl"
    index_path.write_bytes(b"corrupt")
    _write_meta(meta_path, [])
    data_path.write_text(
        '{"poi_id":"cafe_1","poi_name":"Quiet Cafe","city":"hefei",'
        '"reviews":[{"content":"quiet cafe for working","rating":4.8}]}',
        encoding="utf-8",
    )
    monkeypatch.setitem(
        sys.modules,
        "faiss",
        SimpleNamespace(read_index=lambda path: (_ for _ in ()).throw(RuntimeError("bad index"))),
    )
    monkeypatch.setattr(
        "app.repositories.ugc_vector_repo.SentenceTransformer",
        lambda model_name: FakeModel(),
        raising=False,
    )

    repo = UgcVectorRepo(data_path, faiss_index_path=index_path, meta_path=meta_path)
    hits = repo.search("quiet cafe", top_k=1)

    assert [hit.poi_id for hit in hits] == ["cafe_1"]
