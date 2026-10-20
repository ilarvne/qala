#!/usr/bin/env python3
"""Run the complete open-data collection pipeline with staged dataset output.

uv run python scripts/refresh_dataset.py --live
uv run python scripts/refresh_dataset.py --replay
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def retain_operator_corrections(dataset: dict, project_root: Path = ROOT) -> dict:
    try:
        from apply_operator_corrections import apply_retained_operator_corrections
    except ModuleNotFoundError:
        from scripts.apply_operator_corrections import apply_retained_operator_corrections
    return apply_retained_operator_corrections(dataset, project_root)


def merge_retained_collections(dataset: dict, project_root: Path = ROOT) -> dict:
    """Apply collected open-source records deterministically, without network."""
    path = project_root / "data/raw/overture-astana-places.json"
    if path.is_file():
        try:
            from collect_overture_places import merge_overture
        except ModuleNotFoundError:
            from scripts.collect_overture_places import merge_overture
        boundary = project_root / "data/raw/astana-boundary-geometry.json"
        if not boundary.is_file():
            raise ValueError("Retained Overture collection lacks city polygon evidence")
        dataset, _ = merge_overture(dataset, json.loads(path.read_text()), json.loads(boundary.read_text()))
    media = project_root / "data/raw/media-upgrade-evidence.json"
    if media.is_file():
        try:
            from discover_poi_media import apply_verified_media_patches
            from merge_wikidata_places import merge_wikidata
        except ModuleNotFoundError:
            from scripts.discover_poi_media import apply_verified_media_patches
            from scripts.merge_wikidata_places import merge_wikidata
        sidecar = json.loads(media.read_text())
        apply_verified_media_patches(dataset, sidecar)
        dataset, _ = merge_wikidata(dataset, sidecar, json.loads((project_root / "data/raw/astana-boundary-geometry.json").read_text()))
    try:
        from scripts.publish_curated_expansion import apply_retained_expansion
    except ModuleNotFoundError:
        from publish_curated_expansion import apply_retained_expansion
    dataset = apply_retained_expansion(dataset, project_root)
    return retain_operator_corrections(dataset, project_root)


def enrich_retained_descriptions(dataset: dict, entities: dict) -> None:
    """Wikidata descriptions remain linked facts, never inferred venue claims."""
    for poi in dataset["pois"]:
        entity = entities.get(poi.get("wikidata"), {})
        descriptions = {lang: value["value"] for lang, value in entity.get("descriptions", {}).items() if lang in {"en", "ru", "kk"}}
        if descriptions:
            poi["descriptions"] = descriptions
        if descriptions.get("en") and poi["description_derived"]:
            poi["description"] = descriptions["en"]
            poi["description_derived"] = False
            poi["description_source"] = {"name": "Wikidata", "url": "https://www.wikidata.org/wiki/" + entity["id"], "license": "CC0"}


def replay_dataset(project_root: Path = ROOT) -> dict:
    """Reparse retained public evidence without any network or dataset write."""
    try:
        from collect_pois import transform, coverage, enrich_official
        from enrich_poi_media import commons_photo
        from enrich_poi_reviews import enrich_reviews
    except ModuleNotFoundError:
        from scripts.collect_pois import transform, coverage, enrich_official
        from scripts.enrich_poi_media import commons_photo
        from scripts.enrich_poi_reviews import enrich_reviews
    retained = json.loads((project_root / "data/pois.json").read_text())
    raw = json.loads((project_root / "data/raw/astana-overpass-citywide.json").read_text())
    result = transform(raw, retained["metadata"]["endpoint"], retained["metadata"]["collected_at"])
    if retained["metadata"].get("additional_collections"):
        result = merge_retained_collections(result, project_root)
    by_id = {p["id"]: p for p in result["pois"]}
    originals = {p["id"]: p for p in retained["pois"]}
    operator_sources = {}
    entities, pages = {}, {}
    for path in sorted((project_root / "data/raw/media").glob("*.json")):
        value = json.loads(path.read_text())
        entities.update(value.get("entities", {}))
        for page in value.get("query", {}).get("pages", {}).values():
            pages[page["title"]] = page
    if retained["metadata"].get("curated_media_expansion"):
        try:
            from scripts.publish_curated_expansion import retained_expansion_pages
        except ModuleNotFoundError:
            from publish_curated_expansion import retained_expansion_pages
        pages.update(retained_expansion_pages(project_root))
    enrich_retained_descriptions(result, entities)
    for poi in result["pois"]:
        # The final attribution manifest is authoritative after identity replay;
        # stage patches and new candidate rows may already contain these images.
        poi["photos"] = []
        poi["image"] = None
        original = originals.get(poi["id"], {})
        operator = original.get("hours_source", {}).get("url")
        expected = {"https://www.nmrk.kz/en/": "national-museum-operator.html", "https://a-vm.kz/en/objects/bayterek/": "baiterek-operator.html"}
        if operator in expected:
            snapshot = project_root / "data/raw" / expected[operator]
            if snapshot.is_file() and snapshot.stat().st_size:
                operator_sources[operator] = {"html": snapshot.read_text(), "observed_at": original["hours_source"]["collected_at"]}
            else:
                excerpts = json.loads((project_root / "data/raw/operator-source-excerpts.json").read_text())["sources"]
                evidence = next((item for item in excerpts if item["url"] == operator), None)
                if not evidence or len(" ".join(evidence["excerpts"]).split()) > 25 or hashlib.sha256("\n".join(evidence["excerpts"]).encode()).hexdigest() != evidence["excerpts_sha256"]:
                    raise ValueError("Missing or invalid retained operator evidence")
                operator_sources[operator] = {"html": " ".join(evidence["excerpts"]), "observed_at": evidence["observed_at"]}
    enrich_official(result, offline_sources=operator_sources)
    media = json.loads((project_root / "data/photo-attributions.json").read_text())
    excluded = set(json.loads((project_root / "data/photo-curation.json").read_text()).get("excluded_files", {}))
    for item in media["photos"]:
        title = "File:" + item["title"]
        if title in excluded:
            raise ValueError("Excluded source photograph appeared in published manifest")
        proof = commons_photo(pages.get(title, {}), item["observed_at"])
        if not proof or any(proof[field] != item[field] for field in ("source_url", "author", "license", "license_url")):
            raise ValueError("Photo evidence does not match retained Commons metadata")
        poi = by_id[item["poi_id"]]
        curated_identity = any(proof.get("source_url") == item["source_url"] for proof in poi.get("media_identity_evidence", []))
        if not (poi.get("wikidata") or poi["raw_tags"].get("wikimedia_commons") or curated_identity):
            raise ValueError("Photo target lacks exact source entity link")
        if item["url"].startswith("/photos/") and not (project_root / "public" / item["url"].lstrip("/")).is_file():
            raise ValueError("Missing cached photograph")
        photo = {k: v for k, v in item.items() if k not in {"poi_id", "poi_name"}}
        poi["photos"].append(photo)
        poi["image"] = poi["photos"][0]["url"]
    result["metadata"]["media_enrichment"] = media["metadata"]
    review_source = json.loads((project_root / "data/raw/mangrove-astana-bbox.json").read_text())
    enrich_reviews(result, review_source, retained["metadata"]["reviews_enrichment"]["collected_at"])
    retain_operator_corrections(result, project_root)
    result["metadata"]["coverage"] = coverage(result["pois"])
    if result["metadata"]["coverage"] != retained["metadata"]["coverage"]:
        raise ValueError("Replay coverage differs from published dataset")
    return result


def refresh_live(project_root: Path = ROOT, raw_input: Path | None = None, run=None) -> dict:
    """Publish six normalized files together; raw/media caches are audit output."""
    try:
        from export_poi_dataset import export_dataset
    except ModuleNotFoundError:
        from scripts.export_poi_dataset import export_dataset
    run = run or subprocess.run
    destination = project_root / "data"
    destination.mkdir(parents=True, exist_ok=True)
    names = ("photo-attributions.json", "review-attributions.json", "photo-curation.json")
    previous = {name: (destination / name).read_bytes() if (destination / name).exists() else None for name in names}
    with tempfile.TemporaryDirectory(prefix="qala-poi-refresh-", dir=destination) as directory:
        stage = Path(directory)
        staged = stage / "pois.json"
        sidecars = {}
        try:
            command = [sys.executable, str(project_root / "scripts/collect_pois.py"), "--output", str(staged)]
            if raw_input:
                command += ["--input", str(raw_input)]
            run(command, cwd=project_root, check=True)
            # A fresh OSM collection must not silently discard licensed source
            # additions. Live Overture refresh is explicit; cached source replay
            # requires neither DuckDB nor another network transfer.
            collected = merge_retained_collections(json.loads(staged.read_text()), project_root)
            staged.write_text(json.dumps(collected, ensure_ascii=False, indent=2))
            run([sys.executable, str(project_root / "scripts/enrich_poi_media.py"), "--input", str(staged), "--cache"], cwd=project_root, check=True)
            run([sys.executable, str(project_root / "scripts/enrich_poi_reviews.py"), "--dataset", str(staged)], cwd=project_root, check=True)
            corrected = retain_operator_corrections(json.loads(staged.read_text()), project_root)
            staged.write_text(json.dumps(corrected, ensure_ascii=False, indent=2))
            for name in names:
                if (destination / name).is_file():
                    sidecars[name] = stage / name
                    shutil.copyfile(destination / name, sidecars[name])
        finally:
            # Existing collectors emit their attribution manifests next to the
            # corpus. Restore them until validation and export can commit all
            # normalized files as one rollback unit.
            for name, content in previous.items():
                if content is None:
                    (destination / name).unlink(missing_ok=True)
                else:
                    (destination / name).write_bytes(content)
        return export_dataset(staged, project_root=project_root, sidecars=sidecars)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true", help="Collect fresh public OSM, operator, Commons and Mangrove evidence; publish after all stages succeed")
    mode.add_argument("--replay", action="store_true", help="Reparse and verify retained evidence without network access or changing the published dataset")
    parser.add_argument("--raw", type=Path, help="Use a retained Overpass response instead of downloading it again")
    parser.add_argument("--overture", action="store_true", help="With --live, refresh the spatially selective Overture Places snapshot before publication (optional duckdb dependency)")
    args = parser.parse_args()
    if args.replay:
        replayed = replay_dataset()
        print(json.dumps({"mode": "offline-replay", "dataset_preserved": True, "sha256": hashlib.sha256((ROOT / "data/pois.json").read_bytes()).hexdigest(), "coverage": replayed["metadata"]["coverage"]}, indent=2))
        return
    if args.overture:
        try:
            from collect_overture_places import collect
        except ModuleNotFoundError:
            from scripts.collect_overture_places import collect
        collect(ROOT)
    manifest = refresh_live(ROOT, args.raw)
    print(json.dumps({"coverage": manifest["metadata"]["coverage"], "validation": manifest["validation"]}, indent=2))


if __name__ == "__main__":
    main()
