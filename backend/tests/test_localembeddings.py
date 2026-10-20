"""Neural cache lifecycle: zero implicit downloads and exact content identity."""
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

import pytest

from backend.localembeddings import CACHE_VERSION, DIMENSION, MODEL, CachedFastEmbedEmbeddings, document_hash
from backend.retrieval import HybridPOIRetriever


def make_cache(path, texts):
    import array
    (path / "models" / "cached-model").mkdir(parents=True)
    manifest = {"version": CACHE_VERSION, "model": MODEL, "cache_key": MODEL + "@fixture", "dimension": DIMENSION, "model_directory": "models/cached-model"}
    (path / "manifest.json").write_text(json.dumps(manifest))
    with sqlite3.connect(path / "vectors.sqlite3") as connection:
        connection.execute("CREATE TABLE embeddings (model TEXT, content_hash TEXT, vector BLOB)")
        for text in texts:
            connection.execute("INSERT INTO embeddings VALUES (?, ?, ?)", (MODEL + "@fixture", document_hash(text), array.array("f", [1.0] + [0.0] * (DIMENSION - 1)).tobytes()))


def test_uncached_local_mode_falls_back_without_touching_model_provider(tmp_path, monkeypatch):
    def forbidden(**kwargs):
        raise AssertionError("Runtime must not try to download a missing model")
    monkeypatch.setitem(sys.modules, "fastembed", SimpleNamespace(TextEmbedding=forbidden))
    monkeypatch.setenv("QALA_EMBEDDINGS", "local")
    monkeypatch.setenv("QALA_EMBEDDING_CACHE", str(tmp_path))
    poi = {"id": "test", "name": "Cafe", "description": "Coffee", "category": "cafe", "tags": ["coffee"], "source": {"url": "https://www.openstreetmap.org/node/1"}, "lat": 51.1, "lon": 71.4, "indoor": True, "wheelchair": "unknown"}
    retriever = HybridPOIRetriever([poi])
    assert retriever.embedding_mode == "local-feature-hash-cache-unavailable"
    assert retriever.search("coffee", (51.1, 71.4), ["coffee"], False, False, 1000)


def test_stale_content_is_rejected_before_model_loading(tmp_path, monkeypatch):
    make_cache(tmp_path, ["Old document"])
    def forbidden(**kwargs):
        raise AssertionError("A stale corpus must fail before model loading")
    monkeypatch.setitem(sys.modules, "fastembed", SimpleNamespace(TextEmbedding=forbidden))
    with pytest.raises(ValueError, match="stale"):
        CachedFastEmbedEmbeddings(tmp_path, ["Edited document"])


def test_cached_document_lookup_does_not_infer_or_download(tmp_path, monkeypatch):
    import numpy as np
    make_cache(tmp_path, ["Source document"])
    called = []
    class CachedModel:
        def __init__(self, **kwargs):
            called.append(kwargs)
            assert kwargs["local_files_only"] is True and kwargs["threads"] == 2
            assert kwargs["providers"] == ["CPUExecutionProvider"]
            assert Path(kwargs["specific_model_path"]).is_dir()
        def passage_embed(self, texts, **kwargs):
            raise AssertionError("Runtime document vectors must come from the cache")
        def query_embed(self, text):
            yield np.asarray([.5] * DIMENSION, dtype=np.float32)
    monkeypatch.setitem(sys.modules, "fastembed", SimpleNamespace(TextEmbedding=CachedModel))
    embeddings = CachedFastEmbedEmbeddings(tmp_path, ["Source document"])
    assert len(called) == 1
    assert embeddings.embed_documents(["Source document"])[0] == [1.0] + [0.0] * (DIMENSION - 1)
    assert len(embeddings.embed_query("A new question")) == DIMENSION
    with pytest.raises(ValueError, match="missing"):
        embeddings.embed_documents(["Uncached new document"])


def test_manifest_cannot_point_outside_embedding_cache(tmp_path):
    make_cache(tmp_path, ["Source document"])
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["model_directory"] = ".."
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(FileNotFoundError, match="directory"):
        CachedFastEmbedEmbeddings(tmp_path, ["Source document"])
