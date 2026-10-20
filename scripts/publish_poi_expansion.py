#!/usr/bin/env python3
"""Publish collected source expansions with curated media and complete evidence.

Collectors produce staging files first. This operator entry point copies only
referenced, curated photographs, retains replay JSON, checks identities/facts,
then publishes normalized data, exports and attribution/curation as one rollback
unit. Raw evidence/cache writes remain separate audit artifacts on failure.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

try:
    from scripts.collect_pois import coverage, write_json
    from scripts.discover_poi_media import apply_verified_media_patches
    from scripts.enrich_poi_reviews import enrich_reviews
    from scripts.export_poi_dataset import export_dataset
    from scripts.merge_wikidata_places import merge_wikidata
    from scripts.refresh_dataset import enrich_retained_descriptions, replay_dataset
except ModuleNotFoundError:
    from collect_pois import coverage, write_json
    from discover_poi_media import apply_verified_media_patches
    from enrich_poi_reviews import enrich_reviews
    from export_poi_dataset import export_dataset
    from merge_wikidata_places import merge_wikidata
    from refresh_dataset import enrich_retained_descriptions, replay_dataset

ROOT = Path(__file__).resolve().parents[1]


def publish(candidate_path: Path, media_stage: Path, project_root: Path = ROOT) -> dict:
    baseline = json.loads((project_root / "data/pois.json").read_text())
    candidate = json.loads(candidate_path.read_text())
    sidecar = json.loads((media_stage / "enrichment-sidecar.json").read_text())
    boundary = json.loads((project_root / "data/raw/astana-boundary-geometry.json").read_text())
    apply_verified_media_patches(candidate, sidecar)
    candidate, reconciliation = merge_wikidata(candidate, sidecar, boundary)
    data = project_root / "data"
    discovery = data / "raw/media-discovery"
    discovery.mkdir(parents=True, exist_ok=True)
    for path in sorted(media_stage.glob("*.json")):
        if path.name in {"enrichment-sidecar.json", "photo-curation.json"}: continue
        shutil.copyfile(path, discovery / path.name)
    for path in sorted((media_stage / "commons-raw").glob("*.json")):
        shutil.copyfile(path, data / "raw/media" / ("discovery-" + path.name))
    for path in sorted(media_stage.glob("discovered-entities-*.json")):
        shutil.copyfile(path, data / "raw/media" / ("discovery-" + path.name))
    write_json(data / "raw/media-upgrade-evidence.json", sidecar)
    write_json(data / "raw/wikidata-entity-resolution.json", reconciliation)
    operator_path = media_stage / "operator-source-audit.json"
    if operator_path.is_file():
        operator = json.loads(operator_path.read_text())
        shutil.copyfile(operator_path, data / "raw/operator-source-audit-2026-10-20.json")
        summary = operator.get("summary", {})
        candidate["metadata"]["operator_sources"] = {"collected_at": operator.get("collected_at") or operator.get("observed_at"), "urls_attempted": operator.get("urls_attempted", 0), "urls_collected": operator.get("urls_collected", 0), "network_requests": operator.get("network_requests", 0), "reusable_photos": 0, **summary, "audit_path": "data/raw/operator-source-audit-2026-10-20.json", "policy": "Public operator-page metadata and attributed source links; no unlicensed operator photograph is redistributed"}
    entities = {}
    for path in sorted((data / "raw/media").glob("*.json")):
        payload = json.loads(path.read_text())
        entities.update(payload.get("entities", {}))
    enrich_retained_descriptions(candidate, entities)
    reviews = json.loads((media_stage / "reviews-sidecar.json").read_text())
    review_raw = json.loads((media_stage / "mangrove-astana-2026-10-20.json").read_text())
    enrich_reviews(candidate, review_raw, reviews["metadata"]["collected_at"])
    write_json(data / "raw/mangrove-astana-bbox.json", review_raw)
    curation = json.loads((media_stage / "photo-curation.json").read_text())
    excluded = set(curation.get("excluded_files", {}))
    for poi in candidate["pois"]:
        poi["photos"] = [photo for photo in poi.get("photos", []) if "File:" + photo["title"] not in excluded]
        poi["image"] = poi["photos"][0]["url"] if poi["photos"] else None
        for photo in poi["photos"]:
            if not photo["url"].startswith("/photos/"): continue
            name = Path(photo["url"]).name
            destination = project_root / "public/photos" / name
            staged_photo = media_stage / "photos" / name
            if staged_photo.is_file():
                if destination.is_file() and hashlib.sha256(destination.read_bytes()).digest() != hashlib.sha256(staged_photo.read_bytes()).digest():
                    raise ValueError("Cached source photo identity collision")
                if not destination.is_file(): shutil.copyfile(staged_photo, destination)
            if not destination.is_file(): raise ValueError("Referenced curated photograph is missing")
    candidate["metadata"]["coverage"] = coverage(candidate["pois"])
    candidate["metadata"]["count"] = len(candidate["pois"])
    media_metadata = candidate["metadata"].setdefault("media_enrichment", {})
    media_metadata["pois_with_photos"] = candidate["metadata"]["coverage"]["with_photos"]
    media_metadata["photo_count"] = candidate["metadata"]["coverage"]["photo_count"]
    media_metadata["policy"] = "Exact linked source identity or accepted multilingual-label/coordinate reconciliation; physical source candidates conservatively deduplicated and filtered; reusable license and plaintext author retained; no nearby or generated venue images"
    original_by_id = {poi["id"]: poi for poi in baseline["pois"]}
    new_by_id = {poi["id"]: poi for poi in candidate["pois"]}
    preserved = ("id", "name", "names", "lat", "lon", "category", "poi_type", "hours", "source", "phone", "website", "address", "contact", "amenities", "accessibility", "wheelchair", "indoor", "indoor_evidence")
    if any(identity not in new_by_id or any(new_by_id[identity].get(key) != original.get(key) for key in preserved) for identity, original in original_by_id.items()):
        raise ValueError("Source expansion changed an existing primary venue identity/fact")
    with tempfile.TemporaryDirectory(prefix="qala-curated-publication-", dir=data) as temporary:
        stage = Path(temporary)
        normalized = stage / "pois.json"
        write_json(normalized, candidate)
        photos = {"metadata": deepcopy(media_metadata), "photos": [{"poi_id": poi["id"], "poi_name": poi["name"], **photo} for poi in candidate["pois"] for photo in poi["photos"]]}
        review_manifest = {"metadata": candidate["metadata"]["reviews_enrichment"], "reviews": [{"poi_id": poi["id"], "poi_name": poi["name"], **review} for poi in candidate["pois"] for review in poi.get("reviews", [])]}
        sidecars = {}
        for name, value in (("photo-attributions.json", photos), ("review-attributions.json", review_manifest), ("photo-curation.json", curation)):
            sidecars[name] = stage / name
            write_json(sidecars[name], value)
        # Run the exact portable replay before changing any published normalized
        # file. No full operator HTML, media staging path or network is needed.
        replay_root = stage / "portable-replay"
        (replay_root / "data").mkdir(parents=True)
        (replay_root / "data/pois.json").symlink_to(normalized)
        for name, path in sidecars.items(): (replay_root / "data" / name).symlink_to(path)
        (replay_root / "data/raw").symlink_to(data / "raw", target_is_directory=True)
        (replay_root / "public").symlink_to(project_root / "public", target_is_directory=True)
        replayed = replay_dataset(replay_root)
        if set(new_by_id) != {poi["id"] for poi in replayed["pois"]}:
            raise ValueError("Portable replay changed the candidate identity set")
        manifest = export_dataset(normalized, project_root=project_root, sidecars=sidecars)
    return {"before": len(baseline["pois"]), "after": len(candidate["pois"]), "preserved_primary_records": len(original_by_id), "coverage": candidate["metadata"]["coverage"], "wikidata_resolution": reconciliation["decisions"], "validation": manifest["validation"], "portable_replay": True, "sha256": hashlib.sha256((data / "pois.json").read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--media-stage", type=Path, required=True)
    args = parser.parse_args()
    proof = publish(args.input.resolve(), args.media_stage.resolve())
    write_json(ROOT / "artifacts/poi-expansion-publication-verification.json", proof)
    print(json.dumps(proof, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
