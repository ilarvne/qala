#!/usr/bin/env python3
"""Explicitly download the public model and cache corpus vectors once.

Run this maintenance command before selecting QALA_EMBEDDINGS=local. The API
runtime never downloads weights or computes missing document embeddings.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.localembeddings import CACHE_VERSION, DIMENSION, MODEL, document_hash, poi_document_text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".local/embeddings")
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/pois.json")
    parser.add_argument("--batch-size", type=int, default=32, choices=range(1, 129))
    args = parser.parse_args()
    cache_dir = args.cache_dir.resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    from fastembed import TextEmbedding
    import numpy as np
    dataset = json.loads(args.dataset.read_text())
    texts = list(dict.fromkeys(poi_document_text(poi) for poi in dataset["pois"]))
    hashes = [document_hash(text) for text in texts]
    connection = sqlite3.connect(cache_dir / "vectors.sqlite3", timeout=30)
    connection.execute("CREATE TABLE IF NOT EXISTS embeddings (model TEXT NOT NULL, content_hash TEXT NOT NULL, vector BLOB NOT NULL, PRIMARY KEY (model, content_hash))")
    start = time.perf_counter()
    print(f"Preparing {MODEL}; {len(texts)} unique documents; CPU threads=2", flush=True)
    model = TextEmbedding(model_name=MODEL, cache_dir=str(cache_dir / "models"), threads=2, providers=["CPUExecutionProvider"])
    model_directory = Path(model.model._model_dir).resolve()
    if not model_directory.is_relative_to(cache_dir):
        raise ValueError("Downloaded model is outside the selected cache directory")
    # Bind vectors to the actual tokenizer/ONNX bytes as well as document text.
    fingerprint = hashlib.sha256()
    for path in sorted(model_directory.rglob("*")):
        if path.is_file() and path.suffix in {".onnx", ".json", ".txt", ".model"}:
            fingerprint.update(path.relative_to(model_directory).as_posix().encode())
            with path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    fingerprint.update(chunk)
    cache_key = MODEL + "@" + fingerprint.hexdigest()
    cached = {row[0] for row in connection.execute("SELECT content_hash FROM embeddings WHERE model = ?", (cache_key,))}
    pending = [(text, content_hash) for text, content_hash in zip(texts, hashes) if content_hash not in cached]
    print(f"Embedding {len(pending)} missing documents", flush=True)
    for offset in range(0, len(pending), args.batch_size):
        batch = pending[offset:offset + args.batch_size]
        vectors = list(model.passage_embed([text for text, _ in batch], batch_size=args.batch_size, parallel=None))
        if len(vectors) != len(batch):
            raise ValueError("Embedding provider did not return one vector per document")
        for (_, content_hash), vector in zip(batch, vectors):
            vector = np.asarray(vector, dtype="<f4")
            if vector.shape != (DIMENSION,) or not np.isfinite(vector).all():
                raise ValueError("Embedding provider returned an invalid vector")
            connection.execute("INSERT OR REPLACE INTO embeddings VALUES (?, ?, ?)", (cache_key, content_hash, vector.tobytes()))
        connection.commit()
        if offset % (args.batch_size * 16) == 0 or offset + args.batch_size >= len(pending):
            print(f"Cached {min(offset + args.batch_size, len(pending))}/{len(pending)} new vectors", flush=True)
    connection.close()
    duration = round(time.perf_counter() - start, 2)
    manifest = {"version": CACHE_VERSION, "model": MODEL, "cache_key": cache_key, "dimension": DIMENSION, "license": "Apache-2.0",
                "license_url": "https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2/blob/main/LICENSE",
                "model_source": "https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                "model_directory": model_directory.relative_to(cache_dir).as_posix(), "threads": 2,
                "unique_documents": len(texts), "corpus_fingerprint": hashlib.sha256("".join(sorted(hashes)).encode()).hexdigest(),
                "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(), "generated_at": datetime.now(timezone.utc).isoformat(),
                "prewarm_seconds": duration, "runtime_downloads": False}
    temporary = cache_dir / "manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, indent=2))
    os.replace(temporary, cache_dir / "manifest.json")
    print(f"Ready: {len(texts)} cached vectors; {duration}s; {cache_dir / 'manifest.json'}", flush=True)


if __name__ == "__main__":
    main()
