#!/usr/bin/env python3
"""Explicit live AlemPlus checks; output contains no keys or transcripts."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import os
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
import httpx
from backend.agent import CityAgent
from backend.alemplus import BASE_URL, integration_status, record_status, transcribe_audio
from backend.memory import PreferenceMemory
from backend.models import RecommendRequest


async def check(args):
    load_dotenv(ROOT / ".env")
    dataset = json.loads((ROOT / "data/pois.json").read_text())
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "provider": "AlemPlus", "base_url": BASE_URL,
              "dataset_sha256": hashlib.sha256((ROOT / "data/pois.json").read_bytes()).hexdigest(),
              "privacy": "Only public POI evidence, canonical interests and generated speech fixtures used; no keys, response bodies or transcripts logged.",
              "services": {}, "graph": [], "stt": []}
    async with httpx.AsyncClient(timeout=25, follow_redirects=False) as client:
        for service, key_name, expected_model in [("llm", "ALEMPLUS_API_KEY", "alemllm"), ("embeddings", "ALEMPLUS_EMBED_KEY", "text-1024"),
                                                  ("rerank", "ALEMPLUS_RERANK_KEY", "reranker"), ("stt", "ALEMPLUS_STT_KEY", "speech-to-text"), ("stt_kk", "ALEMPLUS_STT_KK_KEY", "speech-to-text-kk")]:
            key = os.getenv(key_name)
            item = {"configured": bool(key), "expected_model": expected_model}
            if key:
                try:
                    response = await client.get(BASE_URL + "/models", headers={"Authorization": "Bearer " + key})
                    item["auth_status"] = response.status_code
                    item["model_access"] = response.status_code == 200 and expected_model in [model.get("id") for model in response.json().get("data", [])]
                except Exception as error:
                    item["error_type"] = type(error).__name__
            report["services"][service] = item
        if os.getenv("ALEMPLUS_EMBED_KEY"):
            public_poi = next(poi for poi in dataset["pois"] if poi["id"] == "osm-node-4894937300")
            try:
                response = await client.post(BASE_URL + "/embeddings", headers={"Authorization": "Bearer " + os.environ["ALEMPLUS_EMBED_KEY"]},
                                             json={"model": "text-1024", "input": [public_poi["name"] + ". " + public_poi["description"], "A museum visit in Astana"]})
                vectors = [item.get("embedding", []) for item in response.json().get("data", [])] if response.status_code == 200 else []
                verified = len(vectors) == 2 and all(len(vector) == 1024 and all(math.isfinite(float(value)) for value in vector) for vector in vectors)
                record_status("embeddings", verified, status=response.status_code, model="text-1024")
                report["services"]["embeddings"].update(post_status=response.status_code, vectors=len(vectors), dimensions=[len(vector) for vector in vectors], verified=verified, public_poi_id=public_poi["id"], active_runtime_index=False)
            except Exception as error:
                report["services"]["embeddings"]["error_type"] = type(error).__name__
    with tempfile.TemporaryDirectory(prefix="qala-provider-smoke-") as temporary:
        agent = CityAgent(dataset, PreferenceMemory(Path(temporary) / "memory.sqlite3"))
        for language, message in [("en", "A quiet coffee nearby"), ("ru", "Хочу кофе рядом"), ("kk", "Жақын маңда кофе ішкім келеді")]:
            started = time.perf_counter()
            result = await agent.recommend(RecommendRequest(message=message, language=language, location={"lat": 51.1282882, "lon": 71.4304546}, duration_minutes=60, starts_at="2026-10-20T14:00:00+05:00"))
            report["graph"].append({"language": language, "mode": result["mode"], "generation_provider": result["context"].get("generation_provider"),
                                    "rerank_applied": result["retrieval"].get("rerank", {}).get("applied"), "stops": len(result["recommendations"]),
                                    "budget_valid": result["route"]["total_minutes"] <= 60, "poi_ids": [poi["id"] for poi in result["recommendations"]],
                                    "source_grounded": all(poi["source"] == agent.retriever.by_id[poi["id"]]["source"] for poi in result["recommendations"]),
                                    "elapsed_ms": round((time.perf_counter() - started) * 1000)})
    for language, path in [("en", args.audio_en), ("kk", args.audio_kk)]:
        item = {"language": language, "fixture": path.name, "checked": path.is_file()}
        if path.is_file():
            try:
                started = time.perf_counter()
                result = await transcribe_audio(path.read_bytes(), "fixture.mp3", "audio/mpeg", language)
                text = result["text"].casefold()
                item.update(model=result["model"], recognized_nonempty=bool(text), characters=len(text),
                            expected_word_present="кофе" in text if language == "kk" else any(word in text for word in ["walk", "astana", "qala"]),
                            elapsed_ms=round((time.perf_counter() - started) * 1000))
            except Exception as error:
                item["error_type"] = type(error).__name__
        report["stt"].append(item)
    report["integration_status"] = integration_status()
    report["passed"] = all(item.get("model_access") for item in report["services"].values()) and report["services"]["embeddings"].get("verified", False) and all(item["mode"] == "llm-assisted" and item["rerank_applied"] and item["budget_valid"] and item["source_grounded"] for item in report["graph"]) and all(item.get("recognized_nonempty") and item.get("expected_word_present") for item in report["stt"])
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({"passed": report["passed"], "authenticated_services": sum(item.get("model_access", False) for item in report["services"].values()),
                      "llm_graph_languages_verified": sum(item["mode"] == "llm-assisted" for item in report["graph"]),
                      "speech_languages_verified": sum(item.get("recognized_nonempty", False) for item in report["stt"]), "report": str(args.output)}, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio-en", type=Path, default=ROOT / "artifacts/audio/qala-provider-smoke.mp3")
    parser.add_argument("--audio-kk", type=Path, default=ROOT / "artifacts/audio/qala-kazakh-smoke.mp3")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/alemplus-live-verification.json")
    asyncio.run(check(parser.parse_args()))
