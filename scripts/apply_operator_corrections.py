#!/usr/bin/env python3
"""Apply one retained, independently sourced closure correction in memory.

The original Overture entity, name, description and source remain unchanged.
This script writes only an explicitly selected staging file; the transactional
dataset exporter remains the publication owner. Body digests identify acquired
responses; only the bounded excerpt digest is reproducible without private HTML.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
CORRECTION_ID = "nur-alem-museum-closed-2024-12"
GERS_ID = "f156787e-136d-4047-9f5e-8ae04ed039bb"
TARGET_ID = "overture-" + GERS_ID
TARGET_NAME = "Nur Alem Museum of Future Energy"
TARGET_POINT = (51.08931145, 71.41590518)
OPERATOR_URL = "https://qazexpocongress.kz/en/nur-alem/"
SUPPORT_URL = "https://alem.ai/en/"
SIDECAR_NAME = "operator-corrections-2026-10-20.json"


def _digest(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value)


def _point(lat, lon):
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in (lat, lon)):
        raise ValueError("Operator correction requires finite entity coordinates")
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("Operator correction coordinates are outside Earth bounds")
    return lat, lon


def _distance(a, b):
    lat, other = math.radians(a[0]), math.radians(b[0])
    h = math.sin((other - lat) / 2) ** 2 + math.cos(lat) * math.cos(other) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(h)))


def _evidence(sources):
    if not isinstance(sources, list) or not 1 <= len(sources) <= 2:
        raise ValueError("Operator correction requires bounded primary-source evidence")
    checked, words = [], {}
    for source in sources:
        if not isinstance(source, dict) or source.get("url") not in {OPERATOR_URL, SUPPORT_URL}:
            raise ValueError("Unsupported operator correction source")
        excerpts = source.get("excerpts")
        if not isinstance(excerpts, list) or not excerpts or not all(isinstance(item, str) and item.strip() for item in excerpts):
            raise ValueError("Operator source requires exact bounded excerpts")
        origin = urlsplit(source["url"]).netloc
        words[origin] = words.get(origin, 0) + len(" ".join(excerpts).split())
        if words[origin] > 25:
            raise ValueError("Operator excerpt exceeds the per-origin 25-word allowance")
        digest = hashlib.sha256("\n".join(excerpts).encode()).hexdigest()
        if not _digest(source.get("body_sha256")) or source.get("excerpts_sha256") != digest:
            raise ValueError("Invalid operator response or excerpt evidence digest")
        try:
            acquired = datetime.fromisoformat(source["observed_at"].replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ValueError("Operator evidence requires its original acquisition time") from exc
        if acquired.tzinfo is None:
            raise ValueError("Operator evidence acquisition time requires a time zone")
        checked.append({key: copy.deepcopy(source[key]) for key in ("url", "observed_at", "body_sha256", "excerpts", "excerpts_sha256")})
    urls = [source["url"] for source in checked]
    if len(set(urls)) != len(urls) or OPERATOR_URL not in urls:
        raise ValueError("The former museum's operator closure evidence is required")
    closure = " ".join(next(source["excerpts"] for source in checked if source["url"] == OPERATOR_URL))
    if not (re.search(r"\bnur\s+alem\b|\bfuture\s+energy\s+museum\b", closure, re.I)
            and re.search(r"\bDecember\s*,?\s*2024\b", closure, re.I)
            and re.search(r"\b(?:stopped|ceased|closed|no longer|not receiving)\b", closure, re.I)):
        raise ValueError("Operator excerpt does not support this specific museum closure and date")
    return checked


def apply_operator_corrections(dataset: dict, sidecar: dict) -> dict:
    """Validate everything before changing only the obsolete museum's status."""
    if not isinstance(sidecar, dict) or type(sidecar.get("schema_version")) is not int or sidecar.get("schema_version") != 1:
        raise ValueError("Unsupported operator correction schema")
    corrections = sidecar.get("corrections")
    if not isinstance(corrections, list) or len(corrections) != 1:
        raise ValueError("Only the explicitly scoped museum correction is supported")
    correction = corrections[0]
    if not isinstance(correction, dict) or correction.get("id") != CORRECTION_ID:
        raise ValueError("Unknown operator correction")
    target = correction.get("target")
    if not isinstance(target, dict) or any(target.get(key) != value for key, value in
                                          {"id": TARGET_ID, "name": TARGET_NAME, "source_name": "Overture Maps", "gers_id": GERS_ID}.items()):
        raise ValueError("Operator correction target identity is not the obsolete Overture museum")
    target_point = _point(target.get("lat"), target.get("lon"))
    if _distance(target_point, TARGET_POINT) > 100:
        raise ValueError("Operator target evidence is outside the known museum location")
    facts = correction.get("facts")
    if (not isinstance(facts, dict) or facts != {"operating_status": "closed", "recommendable": False, "closed_since": "2024-12"}
            or facts.get("recommendable") is not False):
        raise ValueError("Operator correction may only disable the historical museum")
    sources = _evidence(correction.get("sources"))
    matches = [poi for poi in dataset.get("pois", []) if poi.get("id") == TARGET_ID]
    if len(matches) != 1:
        raise ValueError("Operator correction requires exactly one existing target entity")
    poi = matches[0]
    source = poi.get("source")
    if poi.get("name") != TARGET_NAME or not isinstance(source, dict) or source.get("name") != "Overture Maps" or source.get("gers_id") != GERS_ID:
        raise ValueError("Existing target name or original source identity differs")
    url = urlsplit(source.get("url", ""))
    if url.scheme != "https" or url.netloc != "explore.overturemaps.org" or parse_qs(url.query).get("id") != [GERS_ID]:
        raise ValueError("Existing target lacks its exact public GERS source link")
    point = _point(poi.get("lat"), poi.get("lon"))
    if _distance(point, target_point) > 100 or _distance(point, TARGET_POINT) > 100:
        raise ValueError("Existing target coordinates do not agree with operator correction identity")
    # Validation is complete. Preserve all original descriptive/provenance data.
    evidence = next(source for source in sources if source["url"] == OPERATOR_URL)
    poi["recommendable"] = False
    poi["operating_status"] = "closed"
    poi["operating_status_source"] = {"name": "QazExpoCongress — former museum operator", **copy.deepcopy(evidence), "closed_since": "2024-12"}
    record = {"id": CORRECTION_ID, "target_id": TARGET_ID, **facts, "sources": sources}
    previous = poi.get("source_corrections", [])
    if not isinstance(previous, list):
        previous = []
    poi["source_corrections"] = [item for item in previous if not isinstance(item, dict) or item.get("id") != CORRECTION_ID] + [copy.deepcopy(record)]
    dataset.setdefault("metadata", {})["operator_corrections"] = {
        "schema_version": 1, "applied": [copy.deepcopy(record)],
        "evidence_validation": "Bounded excerpt hashes are verified offline; response hashes identify acquisition evidence and require private raw bodies for full rehashing."}
    return dataset


def apply_retained_operator_corrections(dataset: dict, project_root: Path = ROOT) -> dict:
    path = project_root / "data/raw" / SIDECAR_NAME
    if path.is_file():
        return apply_operator_corrections(dataset, json.loads(path.read_text()))
    return dataset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--corrections", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="Staging JSON only; publish with export_poi_dataset.py")
    args = parser.parse_args()
    if args.output.resolve() in {args.input.resolve(), (ROOT / "data/pois.json").resolve()}:
        raise ValueError("Operator correction output must be a separate staging file")
    dataset = apply_operator_corrections(json.loads(args.input.read_text()), json.loads(args.corrections.read_text()))
    args.output.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
