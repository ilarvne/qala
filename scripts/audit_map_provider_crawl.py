#!/usr/bin/env python3
"""Replay and reconcile retained Google/2GIS/Yandex crawl observations offline.

This command never retries blocked providers, downloads images or publishes
commercial content into the open POI corpus. Acquisition tools and the actual
transport outcomes are documented beside each provider's retained observations.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.providers.common import correlate
from scripts.providers.review_queue import (build_review_queue, review_csv_rows, comparison_csv_rows, safe_csv_cell,
                                             REVIEW_CSV_FIELDS, COMPARISON_CSV_FIELDS)

DEFAULTS = ["artifacts/provider-crawl/2gis/records.json", "artifacts/provider-crawl/yandex/observations.json", "artifacts/provider-crawl/google/rows.json"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/pois.json")
    parser.add_argument("--input", type=Path, action="append", help="Allowlisted factual provider observation JSON; may be repeated")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/provider-crawl/combined")
    parser.add_argument("--quality-conflicts", type=Path, default=ROOT / "artifacts/provider-crawl/google/quality-conflicts.json",
                        help="Existing evaluation-only operating-status conflicts (default: retained Google audit)")
    parser.add_argument("--no-quality-conflicts", action="store_true", help="Skip optional operating-status conflict input")
    args = parser.parse_args()
    output_files = [args.output / name for name in ("observations.json", "observations.csv", "review-queue.json", "review-queue.csv", "provider-comparisons.csv")]
    if args.dataset.resolve() in {path.resolve() for path in output_files}:
        raise ValueError("Audit output must not overwrite its input POI corpus")
    paths = args.input or [ROOT / name for name in DEFAULTS]
    dataset_bytes = args.dataset.read_bytes()
    data = json.loads(dataset_bytes)
    dataset_before = hashlib.sha256(dataset_bytes).hexdigest()
    rows, inputs = [], {}
    for index, original_path in enumerate(paths):
        path = original_path.resolve()
        content = path.read_bytes()
        # CLI paths are commonly relative; retaining only their basename would
        # overwrite two distinct providers' rows.json provenance entries.
        label = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else f"external/{index}/{path.name}"
        inputs[label] = hashlib.sha256(content).hexdigest()
        payload = json.loads(content)
        records = payload if isinstance(payload, list) else payload.get("observations", payload.get("records", payload.get("rows", [])))
        if not isinstance(records, list):
            raise ValueError("Provider file has no observation array")
        rows.extend(correlate(record, data["pois"]) for record in records)
    # A later observation replaces an earlier one only within the same provider
    # entity. Counts are never filled in from another provider or another date.
    grouped = {}
    for row in sorted(rows, key=lambda item: datetime.fromisoformat(item["observed_at"].replace("Z", "+00:00"))):
        grouped[(row["provider"], row["provider_id"])] = row
    rows = list(grouped.values())
    quality, quality_inputs = [], {}
    if not args.no_quality_conflicts:
        content = args.quality_conflicts.read_bytes()
        key = str(args.quality_conflicts.relative_to(ROOT)) if args.quality_conflicts.is_relative_to(ROOT) else args.quality_conflicts.name
        quality_inputs[key] = hashlib.sha256(content).hexdigest()
        quality = json.loads(content)
        if isinstance(quality, dict):
            quality = quality.get("conflicts", [])
        if not isinstance(quality, list):
            raise ValueError("Quality conflict file has no conflict array")
    queue = build_review_queue(rows, data["pois"], quality)
    dataset_after = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    assert dataset_before == dataset_after
    result = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "mode": "offline_replay", "network_requests": 0,
              "dataset_sha256": dataset_before, "dataset_modified": False, "input_sha256": inputs,
              "observations": rows, "counts": {"observations": len(rows), "matched": sum(bool(row["matched_poi_ids"]) for row in rows),
              "providers": {name: sum(row["provider"] == name for row in rows) for name in ("2gis", "yandex", "google")},
              "rating_observations": sum(row["rating"] is not None for row in rows), "photo_source_links": sum(len(row["photo_source_links"]) for row in rows),
              "downloaded_photographs": 0, "collected_review_texts": 0},
              "quality_input_sha256": quality_inputs, "review_queue_counts": queue["counts"],
              "policy": "Evaluation observations only. Photo links and displayed counters do not constitute licensed media, full review texts or permission to build a derivative provider dataset."}
    queue.update(generated_at=result["generated_at"], dataset_sha256=dataset_before, input_sha256=inputs,
                 quality_input_sha256=quality_inputs)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "observations.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    with (args.output / "observations.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        fields = ["provider", "provider_id", "name", "matched_poi_ids", "lat", "lon", "rating", "rating_scale", "rating_count", "review_count", "source_url", "observed_at", "access_method", "evidence_sha256", "photo_source_links", "review_source_links", "import_policy"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: safe_csv_cell(";".join(row[key]) if isinstance(row[key], list) else row[key]) for key in fields})
    (args.output / "review-queue.json").write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n")
    with (args.output / "review-queue.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=REVIEW_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(review_csv_rows(queue))
    with (args.output / "provider-comparisons.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=COMPARISON_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(comparison_csv_rows(queue))
    assert hashlib.sha256(args.dataset.read_bytes()).hexdigest() == dataset_before
    print(json.dumps(result["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
