#!/usr/bin/env python3
"""Publish/replay a reviewed open-source expansion through the rollback exporter.

All collection has already happened. This module performs no network requests.
New raw source evidence and image caches remain audit artifacts; the normalized
JSON/CSV/GeoJSON/manifest/attribution/curation set uses the existing rollback unit.
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
    from scripts.collect_curated_commons import apply_curated_commons, compile_sidecar, load_captures
    from scripts.collect_named_operator_venues import apply_named_operator_venues
    from scripts.collect_pois import coverage
    from scripts.discover_poi_media import apply_verified_media_patches, resolve_entities
    from scripts.export_poi_dataset import export_dataset
    from scripts.merge_wikidata_places import merge_wikidata, physical_type_compatible
except ModuleNotFoundError:
    from collect_curated_commons import apply_curated_commons, compile_sidecar, load_captures
    from collect_named_operator_venues import apply_named_operator_venues
    from collect_pois import coverage
    from discover_poi_media import apply_verified_media_patches, resolve_entities
    from export_poi_dataset import export_dataset
    from merge_wikidata_places import merge_wikidata, physical_type_compatible

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = "data/raw/curated-media-expansion-2026-10-20"
SELECTIONS = ("curated", "additional-curated", "boulevard-curated")


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def retained_entities(project_root: Path) -> dict:
    entities = {}
    for path in sorted((project_root / "data/raw/media").glob("*.json")):
        entities.update(read(path).get("entities", {}))
    return entities


def retained_expansion_pages(project_root: Path) -> dict:
    pages = {}
    for selection in SELECTIONS:
        folder = project_root / SOURCE_PATH / selection / "source-captures"
        if folder.is_dir():
            pages.update({title: page for title, (page, _) in load_captures(folder).items()})
    return pages


def _correct_derived_fountain_identity(dataset: dict, correction: dict, entities: dict) -> None:
    """Remove only the documented derived circus↔fountain conflict, idempotently."""
    target = "osm-way-1134744434"
    qid = "Q21843144"
    if correction.get("poi_id") != target or correction.get("before", {}).get("wikidata") != qid:
        raise ValueError("Unexpected derived identity correction")
    matches = [poi for poi in dataset["pois"] if poi["id"] == target]
    if len(matches) != 1:
        raise ValueError("Fountain correction requires exactly one source target")
    poi = matches[0]
    entity = entities.get(qid, {})
    classes = {claim.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
               for claim in entity.get("claims", {}).get("P31", []) if claim.get("rank") != "deprecated"}
    if (poi.get("poi_type") != "fountain" or poi.get("raw_tags", {}).get("wikidata")
            or poi.get("source", {}).get("url") != "https://www.openstreetmap.org/way/1134744434"
            or classes != {"Q16889960"} or physical_type_compatible(poi, classes)
            or poi.get("wikidata") not in {None, qid}):
        raise ValueError("Source evidence does not support this derived identity correction")
    derived = set(correction["before"].get("aliases", []))
    poi["wikidata"] = None
    poi["aliases"] = [alias for alias in poi.get("aliases", []) if alias not in derived]
    poi["additional_sources"] = [source for source in poi.get("additional_sources", [])
                                 if source.get("url") != "https://www.wikidata.org/wiki/" + qid]


def apply_expansion(dataset: dict, source_root: Path, project_root: Path = ROOT) -> dict:
    """Replay source proof before merging any selected facts or photographs."""
    result = deepcopy(dataset)
    entities = retained_entities(project_root)
    _correct_derived_fountain_identity(result, read(source_root / "derived-identity-correction.json"), entities)
    identity = read(source_root / "additional-identity-evidence.json")
    resolved, _ = resolve_entities(result["pois"], entities)
    if set(identity.get("pois", {})) != {"osm-way-240592107"} or resolved.get("osm-way-240592107") != "Q1899549":
        raise ValueError("Retained reverse OSM source identity does not resolve the cathedral")
    apply_verified_media_patches(result, identity)
    historical_wikidata = deepcopy(result["metadata"].get("wikidata_collection"))
    result, resolution = merge_wikidata(result, read(source_root / "additional-wikidata-candidates.json"),
        read(project_root / "data/raw/astana-boundary-geometry.json"))
    if historical_wikidata is not None:
        result["metadata"]["wikidata_collection"] = historical_wikidata
    result = apply_named_operator_venues(result, read(source_root / "named-operator-venues.json"))
    accepted = []
    for selection in SELECTIONS:
        folder = source_root / selection
        sidecar = read(folder / "sidecar.json")
        replay = compile_sidecar(result, read(folder / "seeds.json"), load_captures(folder / "source-captures"))
        expected = {(row["poi_id"], row["photo"]["source_url"]): row for row in replay["assignments"]}
        proposed = sidecar.get("assignments", [])
        if len(proposed) != len(expected):
            raise ValueError("Staged photo assignments differ from independently compiled source proof")
        for assignment in proposed:
            photo = assignment["photo"]
            proof = expected.get((assignment["poi_id"], photo["source_url"]))
            if proof is None or any(proof.get(key) != assignment.get(key) for key in
                ("target_fingerprint", "identity", "source_metadata", "source_description_sha256", "preferred_cover")):
                raise ValueError("Staged identity evidence differs from retained source compilation")
            if any(proof["photo"].get(key) != photo.get(key) for key in
                ("source_url", "title", "author", "license", "license_url", "attribution", "provider", "observed_at", "width", "height", "restrictions")):
                raise ValueError("Staged attribution differs from retained Commons source metadata")
            filename = Path(photo.get("url", "")).name
            if (photo.get("url") != "/photos/" + filename or Path(filename).suffix not in {".jpg", ".png", ".webp"}
                    or Path(filename).stem != hashlib.sha256(photo["source_url"].encode()).hexdigest()[:20]):
                raise ValueError("Unexpected staged source asset identity")
            asset = project_root / "public/photos" / filename
            if not asset.is_file() or hashlib.sha256(asset.read_bytes()).hexdigest() != photo.get("asset_sha256"):
                raise ValueError("Staged photo bytes differ from immutable acquired asset hash")
        result = apply_curated_commons(result, sidecar)
        accepted.extend(proposed)
    result["metadata"]["curated_media_expansion"] = {
        "source_path": SOURCE_PATH, "photo_assignments": len(accepted),
        "photo_venues": len({row["poi_id"] for row in accepted}),
        "unique_photo_sources": len({row["photo"]["source_url"] for row in accepted}),
        "original_acquisition_times": sorted({row["photo"]["observed_at"] for row in accepted}),
        "additional_wikidata_ids": sorted(row["qid"] for row in resolution["records"]),
        "identity_method": "Explicit editorial description review bound to exact local source identity; reverse Wikidata OSM IDs for the cathedral; physical-type contradictions rejected; no proximity-only assignment",
        "operator_scope": "Alem.ai exterior landmark; museum component hours are separate and do not imply office-centre opening or interior access"}
    result["metadata"].update(count=len(result["pois"]), coverage=coverage(result["pois"]))
    result["metadata"].setdefault("media_enrichment", {}).update(
        pois_with_photos=result["metadata"]["coverage"]["with_photos"],
        photo_count=result["metadata"]["coverage"]["photo_count"])
    return result


def apply_retained_expansion(dataset: dict, project_root: Path = ROOT) -> dict:
    """Unpublished raw audit files alone cannot enable a new catalogue state."""
    if not (project_root / SOURCE_PATH).is_dir():
        return dataset
    retained = project_root / "data/pois.json"
    marker = read(retained).get("metadata", {}).get("curated_media_expansion") if retained.is_file() else None
    if marker is None:
        return dataset
    if not isinstance(marker, dict) or marker.get("source_path") != SOURCE_PATH:
        raise ValueError("Unexpected curated expansion provenance marker")
    return apply_expansion(dataset, project_root / SOURCE_PATH, project_root)


def publish(stage: Path, project_root: Path = ROOT) -> dict:
    """Validate portable replay, then export normalized files as one rollback set."""
    from PIL import Image
    try:
        from scripts.refresh_dataset import replay_dataset
    except ModuleNotFoundError:
        from refresh_dataset import replay_dataset
    baseline = read(project_root / "data/pois.json")
    raw = project_root / SOURCE_PATH
    if baseline.get("metadata", {}).get("curated_media_expansion"):
        # The normalized rollback set points at these exact source bytes.
        # A failed future export must not invalidate the previous snapshot.
        # A new campaign requires a new, explicitly versioned source path.
        active = {path.relative_to(raw): path.read_bytes() for path in raw.rglob("*") if path.is_file()}
        proposed = {path.relative_to(stage / "raw"): path.read_bytes() for path in (stage / "raw").rglob("*") if path.is_file()}
        if not active or active != proposed:
            raise ValueError("Active expansion evidence is immutable; use a separately versioned campaign for changed source proof")
    else:
        raw.mkdir(parents=True, exist_ok=True)
        shutil.copytree(stage / "raw", raw, dirs_exist_ok=True)
    assets = project_root / "public/photos"
    for source in sorted((stage / "photos").iterdir()):
        if source.suffix not in {".jpg", ".png", ".webp"}:
            raise ValueError("Only selected photographic assets may be published")
        with Image.open(source) as picture:
            picture.verify()
        target = assets / source.name
        if target.exists():
            if target.read_bytes() != source.read_bytes():
                raise ValueError("Published source asset identity collision")
        else:
            shutil.copyfile(source, target)
    candidate = apply_expansion(baseline, raw, project_root)
    original = {poi["id"]: poi for poi in baseline["pois"]}
    current = {poi["id"]: poi for poi in candidate["pois"]}
    primary = ("id", "name", "names", "lat", "lon", "category", "poi_type", "hours", "source", "phone", "website", "address", "contact", "amenities", "accessibility", "wheelchair", "indoor", "indoor_evidence", "operating_status", "recommendable")
    if any(identity not in current or any(current[identity].get(key) != poi.get(key) for key in primary) for identity, poi in original.items()):
        raise ValueError("Curated expansion changed an existing primary venue identity/fact/status")
    with tempfile.TemporaryDirectory(prefix="qala-curated-expansion-", dir=project_root / "data") as temporary:
        working = Path(temporary)
        normalized = working / "pois.json"
        write(normalized, candidate)
        sidecars = {}
        manifest = {"metadata": candidate["metadata"]["media_enrichment"], "photos": [
            {"poi_id": poi["id"], "poi_name": poi["name"], **photo} for poi in candidate["pois"] for photo in poi["photos"]]}
        for name, content in (("photo-attributions.json", manifest), ("photo-curation.json", read(stage / "photo-curation.json")),
                              ("review-attributions.json", read(project_root / "data/review-attributions.json"))):
            sidecars[name] = working / name
            write(sidecars[name], content)
        portable = working / "portable-replay"
        (portable / "data").mkdir(parents=True)
        (portable / "data/pois.json").symlink_to(normalized)
        for name, source in sidecars.items():
            (portable / "data" / name).symlink_to(source)
        (portable / "data/raw").symlink_to(project_root / "data/raw", target_is_directory=True)
        (portable / "public").symlink_to(project_root / "public", target_is_directory=True)
        replayed = replay_dataset(portable)
        if {poi["id"] for poi in replayed["pois"]} != set(current):
            raise ValueError("Portable replay changed curated venue identities")
        if replayed["metadata"]["coverage"] != candidate["metadata"]["coverage"]:
            raise ValueError("Portable replay changed curated coverage")
        export_dataset(normalized, project_root=project_root, sidecars=sidecars)
    replayed = replay_dataset(project_root)
    return {"before": coverage(baseline["pois"]), "after": coverage(candidate["pois"]),
        "preserved_primary_records": len(original), "portable_replay": True, "post_publication_replay": True,
        "source_path": SOURCE_PATH, "sha256": hashlib.sha256((project_root / "data/pois.json").read_bytes()).hexdigest(),
        "replayed_identities": len(replayed["pois"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(publish(args.stage.resolve()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
