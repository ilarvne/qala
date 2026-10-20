#!/usr/bin/env python3
"""Export the audited POI corpus as CSV, GeoJSON and a coverage/hash manifest."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def validate_dataset(dataset: dict, project_root: Path = ROOT) -> dict:
    """Fail before publication, rather than recording false checks as success."""
    pois = dataset.get("pois")
    if not isinstance(pois, list) or not pois:
        raise ValueError("Dataset must contain a nonempty POI list")
    metadata = dataset.get("metadata", {})
    for poi in pois:
        required = ("id", "name", "category", "poi_type", "description", "tags", "source", "lat", "lon", "hours", "wheelchair", "indoor", "rating")
        if not isinstance(poi, dict) or any(key not in poi for key in required):
            raise ValueError("POI is missing normalized fields")
        if any(not isinstance(poi[key], str) or not poi[key].strip() for key in ("id", "name", "category", "poi_type", "description", "wheelchair")):
            raise ValueError("POI has invalid normalized text fields")
        if not isinstance(poi["tags"], list) or not all(isinstance(tag, str) for tag in poi["tags"]) or not isinstance(poi["indoor"], bool):
            raise ValueError("POI has invalid normalized tags/indoor state")
        for field, limit in (("lat", 90), ("lon", 180)):
            value = poi[field]
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or abs(value) > limit:
                raise ValueError("POI has invalid coordinates")
        identity = re.fullmatch(r"osm-(node|way|relation)-(\d+)", poi["id"])
        source = poi["source"]
        if not isinstance(source, dict) or not source.get("collected_at"):
            raise ValueError("POI lacks observed source provenance")
        if identity:
            if source.get("url") != "https://www.openstreetmap.org/" + "/".join(identity.groups()) or source.get("element_type") != identity[1] or source.get("element_id") != int(identity[2]):
                raise ValueError("POI provenance does not match its OSM identity")
        elif overture := re.fullmatch(r"overture-([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})", poi["id"]):
            original_licenses = {item.get("license") for item in source.get("original_sources", []) if isinstance(item, dict) and item.get("license")}
            if source.get("gers_id") != overture[1] or source.get("url") != "https://explore.overturemaps.org/?id=" + overture[1] or not source.get("release") or not source.get("licenses") or set(source["licenses"]) != original_licenses or not original_licenses <= {"CDLA-Permissive-2.0", "Apache-2.0", "CC0-1.0"}:
                raise ValueError("POI provenance does not match its licensed Overture identity")
        elif wikidata := re.fullmatch(r"wikidata-(Q\d+)", poi["id"]):
            coordinate = poi.get("source_p625", {})
            if source.get("url") != "https://www.wikidata.org/wiki/" + wikidata[1] or source.get("entity_id") != wikidata[1] or poi.get("wikidata") != wikidata[1] or source.get("license") not in {"CC0", "CC0-1.0"} or not source.get("p31") or coordinate.get("latitude") != poi["lat"] or coordinate.get("longitude") != poi["lon"]:
                raise ValueError("POI provenance does not match its Wikidata identity")
        else:
            raise ValueError("POI identity has no supported source provenance")
        rating = poi["rating"]
        if rating is not None and (isinstance(rating, bool) or not isinstance(rating, (float, int)) or not math.isfinite(rating) or not 0 <= rating <= 5 or not isinstance(poi.get("rating_count"), int) or poi["rating_count"] < 1 or not isinstance(poi.get("rating_source"), dict) or not str(poi["rating_source"].get("url", "")).startswith("https://")):
            raise ValueError("Rating lacks valid range, count or source")
        if not isinstance(poi.get("photos", []), list) or not isinstance(poi.get("reviews", []), list):
            raise ValueError("POI media/reviews must be lists")
        for photo in poi.get("photos", []):
            if not isinstance(photo, dict) or not all(photo.get(key) for key in ("url", "source_url", "license", "license_url", "attribution")):
                raise ValueError("Photo lacks source, license or credit")
            if photo["url"].startswith("/photos/"):
                target = (project_root / "public" / photo["url"].lstrip("/")).resolve()
                if not target.is_relative_to((project_root / "public/photos").resolve()) or not target.is_file():
                    raise ValueError("Cached photo is missing or outside its asset directory")
            elif not photo["url"].startswith("https://"):
                raise ValueError("Photo URL must be a cached asset or HTTPS source")
        for review in poi.get("reviews", []):
            if not isinstance(review, dict) or review.get("signature_verified") is not True or not all(review.get(key) for key in ("source_url", "license", "license_url", "provider")):
                raise ValueError("Review lacks verified source/license evidence")
    validation = {
        "unique_ids": len({p["id"] for p in pois}) == len(pois),
        "every_poi_has_source_provenance": True,
        "every_osm_poi_has_osm_provenance": True,
        "every_available_rating_has_source": True,
        "every_photo_has_license_and_credit": True,
        "every_review_signature_verified": True,
        "every_cached_photo_exists": True,
        "metadata_count_matches": metadata.get("count") == len(pois) and metadata.get("coverage", {}).get("total") == len(pois),
    }
    if not all(validation.values()):
        raise ValueError("Dataset validation failed: " + ", ".join(key for key, value in validation.items() if not value))
    return validation


def _render_exports(dataset_path: Path, output_dir: Path, project_root: Path, validation: dict, sidecars: dict[str, Path]) -> dict:
    dataset = json.loads(dataset_path.read_text())
    pois = dataset["pois"]
    fields = ["id", "name", "category", "poi_type", "lat", "lon", "description", "hours", "phone", "website", "address", "wheelchair", "indoor", "indoor_evidence", "recommendable", "rating", "rating_count", "review_count", "source_url", "collected_at", "photo_count", "photo_sources"]
    csv_path = output_dir / "pois.csv"
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for poi in pois:
            writer.writerow({**{field: poi.get(field) for field in fields if field not in {"source_url", "collected_at", "photo_count", "photo_sources"}},
                "source_url": poi["source"]["url"], "collected_at": poi["source"]["collected_at"],
                "photo_count": len(poi.get("photos", [])), "photo_sources": " | ".join(p["source_url"] for p in poi.get("photos", []))})
    geojson_path = output_dir / "pois.geojson"
    geojson = {"type": "FeatureCollection", "name": "Astana source-backed POIs", "attribution": dataset["metadata"]["attribution"],
        "features": [{"type": "Feature", "id": p["id"], "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]},
                      "properties": {"id": p["id"], "name": p["name"], "category": p["category"], "poi_type": p["poi_type"], "hours": p["hours"], "wheelchair": p["wheelchair"], "rating": p["rating"], "rating_count": p.get("rating_count"), "source_url": p["source"]["url"]}} for p in pois]}
    geojson_path.write_text(json.dumps(geojson, ensure_ascii=False, separators=(",", ":")))
    paths = [("data/pois.json", dataset_path), ("data/pois.csv", csv_path), ("data/pois.geojson", geojson_path)]
    for name in ("photo-attributions.json", "review-attributions.json", "photo-curation.json"):
        paths.append(("data/" + name, sidecars.get(name, project_root / "data" / name)))
    for evidence in sorted((project_root / "data/raw").rglob("*.json")):
        paths.append((str(evidence.relative_to(project_root)), evidence))
    manifest = {"metadata": dataset["metadata"], "completeness_claim": "All matching mapped features in the retained full-city Overpass snapshot plus documented licensed source additions after geography, category, confidence and identity filters; not a census of all physical establishments or a complete review/photo database.",
        "validation": validation,
        "publication": "Validated and rendered before replacement; JSON/CSV/GeoJSON/manifest and supplied attribution sidecars roll back together on handled publication failures. Raw collection snapshots/media caches remain separate audit artifacts. This is not crash-atomic multi-file storage.",
        "files": [{"path": relative, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for relative, path in paths if path.exists()],
        "individual_content_licenses": {"osm_database": "ODbL-1.0", "overture_places": "Per-source CDLA-Permissive-2.0, Apache-2.0 or CC0-1.0; source.original_sources and source.licenses retain exact licenses. OSM-derived combined database remains ODbL; original permissive source rights are retained.", "wikidata_descriptions": "CC0-1.0", "commons_photos": "Per-file license and author in data/photo-attributions.json", "mangrove_reviews": "Per-review CC-BY-4.0 or CC-BY-SA-4.0 in data/review-attributions.json"}}
    (output_dir / "dataset-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def _publish_files(staged: dict[str, Path], destination: Path, backup_dir: Path) -> None:
    """Restore the previous complete normalized set after a handled write error."""
    existed = {}
    for name in staged:
        target = destination / name
        existed[name] = target.exists()
        if existed[name]:
            shutil.copyfile(target, backup_dir / name)
    replaced = []
    try:
        for name, source in staged.items():
            os.replace(source, destination / name)
            replaced.append(name)
    except BaseException:
        for name in reversed(replaced):
            target = destination / name
            if existed[name]:
                os.replace(backup_dir / name, target)
            else:
                target.unlink(missing_ok=True)
        raise


def export_dataset(dataset_path: Path, *, project_root: Path = ROOT, sidecars: dict[str, Path] | None = None) -> dict:
    """Validate/render first, then publish the complete normalized artifact set.

    The source JSON is never moved before export succeeds. Supplied sidecars
    join the same rollback unit, while raw snapshots/public cache stay separate.
    """
    content = dataset_path.read_bytes()
    dataset = json.loads(content)
    validation = validate_dataset(dataset, project_root)
    destination = project_root / "data"
    destination.mkdir(parents=True, exist_ok=True)
    supplied = sidecars or {}
    if any(name not in {"photo-attributions.json", "review-attributions.json", "photo-curation.json"} for name in supplied):
        raise ValueError("Unsupported normalized sidecar")
    for name, path in supplied.items():
        payload = json.loads(path.read_text())
        if name == "photo-curation.json":
            excluded = set(payload.get("excluded_files", {}))
            if any("File:" + photo.get("title", "") in excluded for poi in dataset["pois"] for photo in poi.get("photos", [])):
                raise ValueError("Excluded photograph appears in candidate corpus")
            continue
        field = "photos" if name.startswith("photo") else "reviews"
        expected = sorted((p["id"], item["source_url"]) for p in dataset["pois"] for item in p.get(field, []))
        actual = sorted((item["poi_id"], item["source_url"]) for item in payload[field])
        if actual != expected:
            raise ValueError("Attribution sidecar does not match normalized corpus: " + name)
    with tempfile.TemporaryDirectory(prefix="qala-poi-export-", dir=destination) as temporary:
        stage = Path(temporary)
        staged_json = stage / "pois.json"
        staged_json.write_bytes(content)
        staged_sidecars = {}
        for name, path in supplied.items():
            staged_sidecars[name] = stage / name
            shutil.copyfile(path, staged_sidecars[name])
        manifest = _render_exports(staged_json, stage, project_root, validation, staged_sidecars)
        files = {name: stage / name for name in ("pois.json", "pois.csv", "pois.geojson", "dataset-manifest.json")}
        files.update(staged_sidecars)
        backup = stage / "backup"
        backup.mkdir()
        _publish_files(files, destination, backup)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/pois.json")
    args = parser.parse_args()
    manifest = export_dataset(args.input)
    print(json.dumps({"coverage": manifest["metadata"]["coverage"], "validation": manifest["validation"]}, indent=2))


if __name__ == "__main__":
    main()
