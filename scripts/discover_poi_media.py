#!/usr/bin/env python3
"""Discover photographed Astana landmarks through linked Wikimedia identities.

Wikipedia geographic search produces candidates, not photo assignments. A
candidate is reconciled with a POI only by exact multilingual name/alias and
consistent Wikidata coordinates, or its already explicit Wikidata identity.
Physical landmarks absent from the source corpus are emitted as separate CC0
candidate rows for the transactional dataset publisher to deduplicate.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import httpx

try:
    from .enrich_poi_media import api, enrich_media, USER_AGENT
    from .poi_source_crawler import normalize, distance_m
    from .merge_wikidata_places import physical_type_compatible
except ImportError:
    from enrich_poi_media import api, enrich_media, USER_AGENT
    from poi_source_crawler import normalize, distance_m
    from merge_wikidata_places import physical_type_compatible

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "artifacts/media-upgrade-staging"
# Source P31 classifications. No political positions, jurisdictions, companies,
# headquarters, transient events, residential districts or schools are POIs.
CLASSES = {
    "Q22698": ("park", "park"), "Q22746": ("park", "urban_park"),
    "Q167346": ("park", "botanical_garden"), "Q23397": ("park", "lake"),
    "Q33506": ("museum", "museum"), "Q2772772": ("museum", "museum"),
    "Q24354": ("culture", "theatre"), "Q153562": ("culture", "opera_house"),
    "Q16889960": ("culture", "circus"), "Q41253": ("culture", "cinema"),
    "Q1060829": ("culture", "concert_hall"), "Q7075": ("culture", "library"),
    "Q22806": ("culture", "library"), "Q4989906": ("culture", "monument"),
    "Q860861": ("culture", "sculpture"), "Q2319498": ("culture", "architectural_landmark"),
    "Q32815": ("culture", "mosque"), "Q34627": ("culture", "synagogue"),
    "Q2977": ("culture", "cathedral"), "Q56242225": ("culture", "cathedral"),
    "Q2031836": ("culture", "church"), "Q44539": ("culture", "temple"),
    "Q41176": ("culture", "building"), "Q1497364": ("culture", "building_complex"),
    "Q174782": ("culture", "square"), "Q12280": ("culture", "bridge"),
    "Q39614": ("culture", "cemetery"), "Q1440300": ("viewpoint", "observation_tower"),
    "Q811979": ("culture", "architectural_structure"),
    "Q54114": ("park", "boulevard"),
    "Q11315": ("shopping", "mall"), "Q27686": ("accommodation", "hotel"),
    "Q483110": ("sport", "stadium"), "Q1154710": ("sport", "stadium"),
    "Q641226": ("sport", "arena"), "Q1076486": ("sport", "sports_centre"),
    "Q12019965": ("sport", "ice_rink"), "Q55488": ("transport", "station"),
    "Q494829": ("transport", "bus_station"),
}


def claims(entity: dict, property_id: str):
    return [s["mainsnak"]["datavalue"]["value"] for s in entity.get("claims", {}).get(property_id, [])
            if s.get("rank") != "deprecated" and s.get("mainsnak", {}).get("datavalue", {}).get("value") is not None]


def entity_coordinates(entity: dict) -> list[dict]:
    return [c for c in claims(entity, "P625") if isinstance(c, dict) and c.get("globe", "").endswith("Q2")
            and all(isinstance(c.get(key), (int, float)) and not isinstance(c[key], bool) and math.isfinite(c[key]) for key in ("latitude", "longitude"))
            and -90 <= c["latitude"] <= 90 and -180 <= c["longitude"] <= 180]


def entity_names(entity: dict) -> set[str]:
    return {v["value"] for v in entity.get("labels", {}).values()} | {a["value"] for rows in entity.get("aliases", {}).values() for a in rows}


def poi_names(poi: dict) -> set[str]:
    names = {poi["name"], *poi.get("names", {}).values()}
    for key, value in poi.get("raw_tags", {}).items():
        if key.startswith("name:") or key in {"alt_name", "old_name", "official_name", "short_name"}:
            names.update(value.split(";"))
    return {normalize(n) for n in names if isinstance(n, str) and len(normalize(n)) >= 4}


def reverse_osm_claims(entity: dict) -> list[str]:
    """Retain exact, nondeprecated way/relation IDs, including duplicate claims."""
    result = []
    for property_id, kind in (("P10689", "way"), ("P402", "relation")):
        for value in claims(entity, property_id):
            if isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value):
                result.append(f"osm-{kind}-{value}")
    return result


def _explicit_osm_identity(poi: dict) -> str | None:
    identity = poi.get("id", "")
    match = re.fullmatch(r"osm-(way|relation)-([1-9][0-9]*)", identity)
    source = poi.get("source", {})
    if match and isinstance(source, dict):
        kind, number = match.groups()
        if (source.get("name") == "OpenStreetMap" and source.get("element_type") == kind
                and type(source.get("element_id")) is int and source["element_id"] == int(number)
                and source.get("url") == f"https://www.openstreetmap.org/{kind}/{number}"):
            return identity
    return None


def resolve_entities(pois: list[dict], entities: dict) -> tuple[dict[str, str], list[dict]]:
    """Conservative entity reconciliation with explicit ambiguity rejection."""
    names_index: dict[str, list[dict]] = {}
    explicit: dict[str, list[dict]] = {}
    osm_index: dict[str, list[dict]] = {}
    for poi in pois:
        if poi.get("wikidata"):
            explicit.setdefault(poi["wikidata"], []).append(poi)
        if not poi.get("name_derived"):
            for name in poi_names(poi):
                names_index.setdefault(name, []).append(poi)
        osm_identity = _explicit_osm_identity(poi)
        if osm_identity:
            osm_index.setdefault(osm_identity, []).append(poi)
    reverse = {qid: reverse_osm_claims(entity) for qid, entity in entities.items()}
    claim_counts = Counter(identity for values in reverse.values() for identity in values)
    resolved, audit, ambiguous = {}, [], set()
    for qid, entity in entities.items():
        class_ids = {value.get("id") for value in claims(entity, "P31") if isinstance(value, dict)}
        if not class_ids.intersection(CLASSES):
            continue
        coordinates = entity_coordinates(entity)
        candidates: dict[str, dict] = {}
        for name in entity_names(entity):
            for poi in names_index.get(normalize(name), []):
                candidates[poi["id"]] = poi
        for poi in explicit.get(qid, []):
            candidates[poi["id"]] = poi
        reverse_candidates, reverse_conflicts = set(), set()
        for identity in reverse[qid]:
            for poi in osm_index.get(identity, []):
                candidates[poi["id"]] = poi
                if claim_counts[identity] != 1 or len(osm_index[identity]) != 1:
                    reverse_conflicts.add(poi["id"])
                else:
                    reverse_candidates.add(poi["id"])
        for poi in candidates.values():
            if poi["id"] in reverse_conflicts:
                audit.append({"poi_id": poi["id"], "qid": qid, "accepted": False,
                              "reason": "ambiguous or duplicate reverse OSM identity claims"})
                continue
            if not physical_type_compatible(poi, class_ids):
                audit.append({"poi_id": poi["id"], "qid": qid, "accepted": False,
                              "reason": "contradictory-physical-types"})
                continue
            distances = [distance_m(poi["lat"], poi["lon"], c["latitude"], c["longitude"]) for c in coordinates]
            explicit_identity = poi.get("wikidata") == qid
            if poi["id"] in ambiguous and not explicit_identity:
                continue
            # An explicit chain-level Wikidata tag is not branch identity.
            if not coordinates or min(distances) > 200:
                audit.append({"poi_id": poi["id"], "qid": qid, "accepted": False,
                              "reason": "missing or contradictory physical coordinates"})
                continue
            if poi.get("wikidata") and not explicit_identity:
                audit.append({"poi_id": poi["id"], "qid": qid, "accepted": False,
                              "reason": "conflicting existing Wikidata identity"})
                continue
            if poi["id"] in resolved and resolved[poi["id"]] != qid:
                # Two exact-name physical entities at one position are
                # ambiguous. Preserve an existing explicit source ID only.
                if not explicit_identity:
                    resolved.pop(poi["id"], None)
                    ambiguous.add(poi["id"])
                    audit.append({"poi_id": poi["id"], "qid": qid, "accepted": False, "reason": "ambiguous entities"})
                    continue
            resolved[poi["id"]] = qid
            audit.append({"poi_id": poi["id"], "qid": qid, "accepted": True,
                          "method": "explicit Wikidata and coordinates" if explicit_identity else
                                    "exact reverse OSM identity claim and coordinates" if poi["id"] in reverse_candidates else
                                    "exact multilingual name/alias and coordinates",
                          "distance_m": round(min(distances), 1)})
    return resolved, audit


def collect_discovery(raw_dir: Path, *, replay: bool = False) -> tuple[dict, dict, list[dict]]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    if not replay:
        with httpx.Client(timeout=35, headers={"User-Agent": USER_AGENT}) as client:
            # Three overlapping windows cover the long north/south city centre
            # and the airport; missing language endpoints are recorded.
            for language in ("en", "ru", "kk"):
                for window, centre in enumerate(("51.128|71.430", "51.213|71.430", "51.040|71.450")):
                    params = {"action": "query", "generator": "geosearch", "ggscoord": centre,
                              "ggsradius": 10000, "ggslimit": 500, "prop": "coordinates|pageprops|pageimages", "piprop": "name"}
                    for index in range(8):
                        try:
                            response = api(client, f"https://{language}.wikipedia.org/w/api.php", params)
                        except (httpx.HTTPError, ValueError) as exc:
                            response = {"error": {"type": type(exc).__name__}}
                        (raw_dir / f"wikipedia-{language}-{window}-{index}.json").write_text(json.dumps(response, ensure_ascii=False))
                        if "continue" not in response:
                            break
                        params.update(response["continue"])
    entities, pages_by_qid, failures = {}, {}, []
    for file in sorted(raw_dir.glob("wikipedia-*.json")):
        response = json.loads(file.read_text())
        language = file.name.split("-")[1].removesuffix(".json")
        if response.get("error"):
            failures.append({"snapshot": file.name, "error": response["error"]})
        for page in response.get("query", {}).get("pages", {}).values():
            qid = page.get("pageprops", {}).get("wikibase_item")
            if qid:
                pages_by_qid.setdefault(qid, []).append({"language": language, "title": page["title"],
                    "image": page.get("pageimage") or page.get("pageprops", {}).get("page_image_free"),
                    "source_url": f"https://{language}.wikipedia.org/wiki/" + quote(page["title"].replace(" ", "_"))})
    if not replay:
        with httpx.Client(timeout=35, headers={"User-Agent": USER_AGENT}) as client:
            for index, start in enumerate(range(0, len(pages_by_qid), 40)):
                result = api(client, "https://www.wikidata.org/w/api.php", {"action": "wbgetentities",
                    "ids": "|".join(sorted(pages_by_qid)[start:start + 40]), "props": "labels|aliases|descriptions|claims|sitelinks", "languages": "en|ru|kk"})
                (raw_dir / f"discovered-entities-{index}.json").write_text(json.dumps(result, ensure_ascii=False))
    for file in sorted(raw_dir.glob("discovered-entities-*.json")):
        entities.update(json.loads(file.read_text()).get("entities", {}))
    return entities, pages_by_qid, failures


def physical_candidate(qid: str, entity: dict, pages: list[dict], observed: str, bbox: list[float]) -> dict | None:
    coordinates = entity_coordinates(entity)
    if not coordinates:
        return None
    coordinate = coordinates[0]
    precision = coordinate.get("precision")
    if not isinstance(precision, (int, float)) or isinstance(precision, bool) or not 0 < precision <= 0.001:
        return None
    if claims(entity, "P576"):
        return None  # dissolved/demolished source entity is not a current POI
    lat, lon = coordinate["latitude"], coordinate["longitude"]
    if not (bbox[0] <= lat <= bbox[2] and bbox[1] <= lon <= bbox[3]):
        return None
    classes = [v.get("id") for v in claims(entity, "P31") if isinstance(v, dict)]
    category = next((CLASSES[c] for c in classes if c in CLASSES), None)
    if not category:
        return None
    labels = {lang: value["value"] for lang, value in entity.get("labels", {}).items() if lang in {"en", "ru", "kk"}}
    if not labels:
        return None
    name = labels.get("en") or labels.get("ru") or labels.get("kk")
    descriptions = {lang: value["value"] for lang, value in entity.get("descriptions", {}).items() if lang in {"en", "ru", "kk"}}
    source = {"name": "Wikidata", "url": "https://www.wikidata.org/wiki/" + qid, "collected_at": observed,
              "license": "CC0", "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
              "entity_id": qid, "p31": classes}
    return {"id": "wikidata-" + qid, "name": name, "names": labels, "name_derived": False,
            "lat": lat, "lon": lon, "category": category[0], "poi_type": category[1],
            "description": descriptions.get("en") or descriptions.get("ru") or name,
            "descriptions": descriptions, "description_derived": not bool(descriptions), "description_source": source if descriptions else None,
            "tags": sorted({category[0], category[1], "nature" if category[0] == "park" else "culture", "walk"}),
            "hours": None, "rating": None, "rating_count": None, "rating_source": None,
            "reviews": [], "review_count": None, "photos": [], "image": None,
            "wheelchair": "unknown", "indoor": None, "indoor_evidence": "unknown",
            "phone": None, "website": next(iter(claims(entity, "P856")), None), "address": None,
            "contact": {"phone": None, "website": next(iter(claims(entity, "P856")), None), "email": None},
            "amenities": {key: None for key in ("internet_access", "power_supply", "outdoor_seating", "toilets", "toilets_wheelchair", "drinking_water", "fee", "access", "lit", "surface")},
            "accessibility": {"wheelchair": "unknown", **{key: None for key in ("wheelchair_description", "entrance", "step_count", "tactile_paving", "hearing_loop")}},
            "wikidata": qid, "wikipedia": (pages[0]["language"] + ":" + pages[0]["title"]) if pages else None,
            "source": source, "raw_tags": {"wikidata": qid}, "duplicate_source_ids": [],
            "coordinates_note": "Wikidata P625 landmark coordinates; entrance and public access not verified",
            "recommendable": True, "entity_aliases": sorted(entity_names(entity)), "source_p625": coordinate,
            "access_note": "Architectural/landscape identity does not establish public entry or current opening hours"}


def apply_verified_media_patches(dataset: dict, sidecar: dict) -> None:
    """Apply only source-proved existing-ID patches during offline replay.

    New candidate deduplication is deliberately owned by the dataset publisher.
    Each existing patch is bound to original coordinates and an accepted
    reconciliation result; unchanged IDs at a new physical place cannot inherit
    the old place's images. File-level Commons licence evidence is checked by
    refresh_dataset's retained-imageinfo replay afterwards.
    """
    by_id = {p["id"]: p for p in dataset["pois"]}
    accepted = {(m["poi_id"], m["qid"]) for m in sidecar.get("identity_audit", []) if m.get("accepted")}
    targets = sidecar.get("target_coordinates", {})
    for poi_id, patch in sidecar.get("pois", {}).items():
        if poi_id not in by_id or not set(patch).issubset({"wikidata", "photos", "image", "media_sources"}):
            raise ValueError("Unknown target or unapproved media patch field")
        poi = by_id[poi_id]
        expected = targets.get(poi_id)
        if not expected or distance_m(poi["lat"], poi["lon"], expected["lat"], expected["lon"]) > 0.1:
            raise ValueError("Media target coordinates differ from retained identity proof")
        qid = patch.get("wikidata") or poi.get("wikidata")
        if (poi_id, qid) not in accepted:
            raise ValueError("Media target lacks accepted entity reconciliation")
        for photo in patch.get("photos", []):
            if not photo.get("source_url", "").startswith("https://commons.wikimedia.org/wiki/File:"):
                raise ValueError("Unexpected photo provider in Wikimedia evidence patch")
            if not photo.get("license") or not photo.get("license_url") or not photo.get("author"):
                raise ValueError("Incomplete reusable image attribution")
        if "photos" in patch:
            expected_image = patch["photos"][0]["url"] if patch["photos"] else None
            if patch.get("image") != expected_image:
                raise ValueError("Photo cover does not match attributed photo order")
        poi.update(copy.deepcopy(patch))
    dataset["metadata"].update(copy.deepcopy(sidecar.get("metadata", {})))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/pois.json")
    parser.add_argument("--staging", type=Path, default=STAGING)
    parser.add_argument("--replay", action="store_true", help="Replay discovery API snapshots; Commons file metadata and thumbnails remain live")
    args = parser.parse_args()
    args.staging.mkdir(parents=True, exist_ok=True)
    observed = datetime.now(timezone.utc).isoformat()
    dataset = json.loads(args.dataset.read_text())
    entities, pages, failures = collect_discovery(args.staging, replay=args.replay)
    resolved, matching = resolve_entities(dataset["pois"], entities)
    by_id = {p["id"]: p for p in dataset["pois"]}
    working = []
    additional = {}
    for poi_id, qid in resolved.items():
        row = copy.deepcopy(by_id[poi_id])
        row["wikidata"] = qid
        working.append(row)
        additional[poi_id] = ["File:" + p["image"] for p in pages.get(qid, []) if p.get("image") and not p["image"].lower().endswith((".svg", ".pdf", ".gif"))]
    existing_qids = {p.get("wikidata") for p in dataset["pois"]} | set(resolved.values())
    candidates = []
    for qid, entity in entities.items():
        if qid in existing_qids:
            continue
        row = physical_candidate(qid, entity, pages.get(qid, []), observed, dataset["metadata"]["bbox"])
        if row is not None:
            working.append(row)
            candidates.append(row)
            additional[row["id"]] = ["File:" + p["image"] for p in pages.get(qid, []) if p.get("image") and not p["image"].lower().endswith((".svg", ".pdf", ".gif"))]
    staged = {"metadata": {}, "pois": working}
    enrich_media(staged, args.staging / "photos", raw_dir=args.staging / "commons-raw", entities_override=entities, additional_titles=additional)
    patches = {}
    for poi in working:
        if poi["id"] not in by_id:
            continue
        before = by_id[poi["id"]]
        patch = {key: poi[key] for key in ("photos", "image", "wikidata") if poi.get(key) != before.get(key)}
        if patch:
            patches[poi["id"]] = patch
    report = {"schema_version": 1, "observed_at": observed,
              "source_dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
              "pois": patches, "new_pois": candidates,
              "target_coordinates": {poi_id: {"lat": by_id[poi_id]["lat"], "lon": by_id[poi_id]["lon"]} for poi_id in patches},
              "metadata": {"media_discovery": {"discovered_entities": len(entities), "reconciled_existing_pois": len(resolved),
                    "patched_existing_pois": len(patches), "physical_candidate_pois": len(candidates),
                    "physical_candidates_with_photos": sum(bool(p.get("photos")) for p in candidates),
                    "reusable_photo_assignments": sum(len(p.get("photos", [])) for p in working),
                    "source_matching": "Exact source Wikidata identity or exact multilingual label/alias plus P625 distance <=200m; physical P31 whitelist for separate candidate POIs",
                    "upstream_errors": failures}, "media_enrichment": staged["metadata"]["media_enrichment"]},
              "identity_audit": matching,
              "publication": "Staged sidecar only. Publisher must deduplicate physical candidates and copy photos atomically with dataset/exports/attributions."}
    (args.staging / "enrichment-sidecar.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report["metadata"]["media_discovery"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
