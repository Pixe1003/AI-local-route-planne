import importlib
import sys
from types import SimpleNamespace

import pytest


np = pytest.importorskip("numpy")


class FakeSentenceTransformer:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def encode(self, texts, normalize_embeddings=True, show_progress_bar=True, batch_size=32):
        return np.array(
            [[1.0, 0.0], [0.0, 1.0]][: len(texts)],
            dtype="float32",
        )


class FakeIndexFlatIP:
    def __init__(self, dim: int) -> None:
        self.dim = dim
        self.vectors = None

    @property
    def ntotal(self) -> int:
        return 0 if self.vectors is None else len(self.vectors)

    def add(self, vectors) -> None:
        self.vectors = vectors


def test_embed_ugc_writes_faiss_index(tmp_path, monkeypatch) -> None:
    data_path = tmp_path / "ugc.jsonl"
    embed_path = tmp_path / "ugc.npy"
    meta_path = tmp_path / "ugc_meta.jsonl"
    index_path = tmp_path / "ugc.faiss"
    data_path.write_text(
        "\n".join(
            [
                '{"poi_id":"cafe_1","poi_name":"Quiet Cafe","reviews":[{"content":"quiet cafe"}]}',
                '{"poi_id":"hotpot_1","poi_name":"Busy Hotpot","reviews":[{"content":"busy hotpot"}]}',
            ]
        ),
        encoding="utf-8",
    )
    written_indexes = {}

    def write_index(index, path: str) -> None:
        written_indexes[path] = index
        index_path.write_bytes(b"fake-faiss")

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )
    monkeypatch.setitem(
        sys.modules,
        "faiss",
        SimpleNamespace(IndexFlatIP=FakeIndexFlatIP, write_index=write_index),
    )
    module = importlib.reload(importlib.import_module("scripts.embed_ugc"))
    monkeypatch.setattr(module, "DATA_PATH", data_path)
    monkeypatch.setattr(module, "EMBED_PATH", embed_path)
    monkeypatch.setattr(module, "META_PATH", meta_path)
    monkeypatch.setattr(module, "FAISS_INDEX_PATH", index_path, raising=False)

    module.main()

    assert embed_path.exists()
    assert meta_path.exists()
    assert index_path.exists()
    assert written_indexes[str(index_path)].dim == 2
    assert written_indexes[str(index_path)].ntotal == 2
