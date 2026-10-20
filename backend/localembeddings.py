"""Opt-in CPU neural embeddings from an explicitly prewarmed local cache.

Runtime never downloads weights or embeds the corpus. Missing/stale caches raise
an exception so the retriever can name and use its portable lexical fallback.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sqlite3
import threading

from langchain_core.embeddings import Embeddings

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DIMENSION = 384
CACHE_VERSION = 1


def document_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def poi_document_text(poi: dict) -> str:
    return " ".join([poi["name"], *poi.get("names", {}).values(), poi["description"], poi["category"], *poi["tags"]])


class CachedFastEmbedEmbeddings(Embeddings):
    def __init__(self, cache_dir: Path, texts: list[str], model_name: str = MODEL):
        self.cache_dir = cache_dir.resolve()
        manifest_path = self.cache_dir / "manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError("Local neural cache has not been prewarmed")
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("version") != CACHE_VERSION or manifest.get("model") != model_name or manifest.get("dimension") != DIMENSION:
            raise ValueError("Local neural cache manifest does not match the selected model")
        self.model_name = model_name
        self.cache_key = manifest.get("cache_key")
        if not isinstance(self.cache_key, str) or not self.cache_key.startswith(model_name + "@"):
            raise ValueError("Local neural cache is missing its model fingerprint")
        self.database = self.cache_dir / "vectors.sqlite3"
        if not self.database.is_file():
            raise FileNotFoundError("Local neural vector cache is missing")
        with self._connection() as connection:
            hashes = {row[0] for row in connection.execute("SELECT content_hash FROM embeddings WHERE model = ?", (self.cache_key,))}
        if not {document_hash(text) for text in texts}.issubset(hashes):
            raise ValueError("Local neural cache is stale; run the explicit prewarm command")
        model_dir = (self.cache_dir / manifest["model_directory"]).resolve()
        if not model_dir.is_relative_to(self.cache_dir) or not model_dir.is_dir():
            raise FileNotFoundError("Local neural model directory is unavailable")
        from fastembed import TextEmbedding
        self.model = TextEmbedding(model_name=model_name, cache_dir=str(self.cache_dir / "models"),
                                   specific_model_path=str(model_dir), local_files_only=True,
                                   providers=["CPUExecutionProvider"], threads=2)
        self._query_lock = threading.Lock()

    def _connection(self):
        # URI read-only mode prevents an accidental empty DB on missing paths.
        return sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True, timeout=10)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        import numpy as np
        output = []
        with self._connection() as connection:
            for text in texts:
                row = connection.execute("SELECT vector FROM embeddings WHERE model = ? AND content_hash = ?", (self.cache_key, document_hash(text))).fetchone()
                if row is None:
                    raise ValueError("A document is missing from the local neural cache")
                vector = np.frombuffer(row[0], dtype="<f4")
                if len(vector) != DIMENSION or not np.isfinite(vector).all():
                    raise ValueError("Invalid cached local neural vector")
                output.append(vector.tolist())
        return output

    def embed_query(self, text: str) -> list[float]:
        with self._query_lock:
            vector = next(iter(self.model.query_embed(text))).tolist()
        if len(vector) != DIMENSION or not all(math.isfinite(float(value)) for value in vector):
            raise ValueError("Invalid local neural query vector")
        return vector
