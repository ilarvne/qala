#!/usr/bin/env python3
"""Real cached-model smoke, network prohibition and semantic retrieval ablation.

Category-labelled probes target implicit phrases absent from the local synonym
ontology. They measure the vector component separately, not end-user correctness.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.localembeddings import MODEL
from backend.retrieval import HybridPOIRetriever, infer_interests

PROBES = [
    ("espresso and cappuccino", "cafe"),
    ("swings and slides", "playground"),
    ("collections of ancient artifacts", "museum"),
    ("trees and fresh air", "park"),
    ("buy clothes and browse stores", "shopping"),
    ("grab a bite", "dining"),
    ("посмотреть старинные экспонаты", "museum"),
    ("покататься на качелях и горках", "playground"),
    ("бұрынғы заман жәдігерлері", "museum"),
    ("әткеншек пен сырғанақ", "playground"),
    ("lift weights", "sport"),
]


def main():
    data = json.loads((ROOT / "data/pois.json").read_text())
    by_id = {poi["id"]: poi for poi in data["pois"]}
    attempts = []
    original_connect, original_create = socket.socket.connect, socket.create_connection
    def forbid_network(*args, **kwargs):
        attempts.append("blocked")
        raise RuntimeError("Network disabled during local neural verification")
    socket.socket.connect, socket.create_connection = forbid_network, forbid_network
    try:
        os.environ["QALA_EMBEDDINGS"] = "hash"
        baseline = HybridPOIRetriever(data["pois"])
        os.environ["QALA_EMBEDDINGS"] = "local"
        started = time.perf_counter()
        neural = HybridPOIRetriever(data["pois"])
        startup_ms = round((time.perf_counter() - started) * 1000, 2)
        if neural.embedding_mode != "fastembed-local-neural":
            raise RuntimeError(f"Local neural cache was not used: {neural.embedding_mode}")
        cases, latencies = [], []
        for query, category in PROBES:
            if infer_interests(query):
                raise ValueError(f"A semantic probe accidentally matches the alias ontology: {query}")
            outputs = {}
            for name, retriever in (("hash", baseline), ("local_neural", neural)):
                start = time.perf_counter()
                matches = retriever.vector.similarity_search_with_score(query, k=5)
                elapsed = round((time.perf_counter() - start) * 1000, 2)
                if name == "local_neural":
                    latencies.append(elapsed)
                items = [{"id": doc.metadata["poi_id"], "name": by_id[doc.metadata["poi_id"]]["name"], "category": doc.metadata["category"], "score": round(float(score), 4)} for doc, score in matches]
                outputs[name] = {"top_5": items, "precision_at_5": sum(item["category"] == category for item in items) / 5,
                                 "top_1_correct": bool(items and items[0]["category"] == category), "local_ms": elapsed}
            cases.append({"query": query, "labelled_category": category, **outputs})
        # An actual final retrieval call proves cached neural queries work in the
        # same geography/category/exclusion pipeline used by the API.
        smoke, diagnostics = neural.search_with_report("Coffee nearby", (51.0897, 71.4073), ["coffee"], False, False, 2000)
        assert smoke and all(poi["category"] == "cafe" for poi in smoke)
        assert diagnostics["embedding_mode"] == "fastembed-local-neural" and diagnostics["vector_query_status"] == "ok"
    finally:
        socket.socket.connect, socket.create_connection = original_connect, original_create
    aggregate = {}
    for name in ("hash", "local_neural"):
        aggregate[name] = {"mean_vector_precision_at_5": round(statistics.mean(case[name]["precision_at_5"] for case in cases), 4),
                           "vector_top_1_category_accuracy": round(statistics.mean(case[name]["top_1_correct"] for case in cases), 4)}
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "dataset_sha256": hashlib.sha256((ROOT / "data/pois.json").read_bytes()).hexdigest(),
              "model": MODEL, "model_license": "Apache-2.0", "mode": neural.embedding_mode, "threads": 2, "dimension": 384,
              "runtime_network_attempts": len(attempts), "network_guard": "socket.connect and create_connection blocked for real model load and every query",
              "startup_ms": startup_ms, "median_neural_vector_query_ms": round(statistics.median(latencies), 2),
              "method": "Full real POI corpus, identical LangChain vector store, feature-hash versus prewarmed FastEmbed, 11 manually category-labelled implicit-language probes with zero alias matches",
              "limitations": "A small diagnostic of the vector component, not a human relevance study, comprehensive multilingual guarantee or final-itinerary accuracy. Geography and hard constraints are tested separately.",
              "aggregate": aggregate, "cases": cases, "hybrid_smoke": {"first_id": smoke[0]["id"], "retrieval": diagnostics}}
    output = ROOT / "artifacts/local-neural-retrieval-verification.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({"mode": neural.embedding_mode, "network_attempts": len(attempts), "aggregate": aggregate, "startup_ms": startup_ms,
                      "median_query_ms": report["median_neural_vector_query_ms"], "report": str(output)}, indent=2))
    if attempts:
        raise SystemExit("Unexpected runtime network attempt")


if __name__ == "__main__":
    main()
