#!/usr/bin/env python3
"""Collect only Astana's Overture Places bbox via selective GeoParquet reads.

Optional live collection dependency: duckdb. Core application/replay
does not need DuckDB. Raw records, STAC, polygon and matching decisions stay
auditable. Existence confidence is never treated as a visitor rating or hours.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from difflib import SequenceMatcher
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlparse

import httpx

try:
    from scripts.collect_pois import BOUNDARY_BBOX, coverage, write_json
except ModuleNotFoundError:
    from collect_pois import BOUNDARY_BBOX, coverage, write_json

ROOT = Path(__file__).resolve().parents[1]
CATALOG = "https://stac.overturemaps.org/catalog.json"
LICENSES = {
    "CDLA-Permissive-2.0": "https://cdla.dev/permissive-2-0/",
    "Apache-2.0": "https://www.apache.org/licenses/LICENSE-2.0",
    "CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
}
MIN_CONFIDENCE = .85


def intersects(bbox: list, target: list) -> bool:
    return bbox[0] <= target[2] and bbox[2] >= target[0] and bbox[1] <= target[3] and bbox[3] >= target[1]


def ring_contains(ring: list, x: float, y: float) -> bool:
    """Ray casting for WGS84 city rings; include a point on the boundary."""
    inside = False
    for a, b in zip(ring, ring[1:]):
        ax, ay = a[:2]; bx, by = b[:2]
        cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax)
        if abs(cross) <= 1e-12 and min(ax, bx) - 1e-12 <= x <= max(ax, bx) + 1e-12 and min(ay, by) - 1e-12 <= y <= max(ay, by) + 1e-12:
            return True
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
    return inside


def boundary_covers(boundary: dict | list, lon: float, lat: float) -> bool:
    geometry = boundary[0]["geojson"] if isinstance(boundary, list) else boundary["geojson"]
    if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("Astana boundary must contain polygon geometry")
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    for rings in polygons:
        if not rings or any(len(ring) < 4 or ring[0] != ring[-1] for ring in rings):
            raise ValueError("Astana polygon contains unclosed rings")
        if ring_contains(rings[0], lon, lat) and not any(ring_contains(hole, lon, lat) for hole in rings[1:]):
            return True
    return False


def collect(project_root: Path = ROOT) -> dict:
    """Use STAC item extents then row-group bbox pushdown, never global COPY."""
    import duckdb

    south, west, north, east = BOUNDARY_BBOX
    target = [west, south, east, north]
    observed = datetime.now(timezone.utc).isoformat()
    with httpx.Client(timeout=40, headers={"User-Agent": "QalaResearch/3.0 (Astana public POIs)"}) as client:
        def fetch(url):
            response = client.get(url)
            response.raise_for_status()
            return response.json()
        catalog = fetch(CATALOG)
        release = catalog["latest"]
        collection = fetch(f"https://stac.overturemaps.org/{release}/places/place/collection.json")
        links = [x["href"] for x in collection["links"] if x["rel"] == "item"]
        with ThreadPoolExecutor(max_workers=4) as executor:
            items = list(executor.map(fetch, links))
        selected = [item for item in items if intersects(item["bbox"], target)]
        urls = [item["assets"]["aws"]["href"] for item in selected]
        if not urls:
            raise ValueError("STAC contains no Astana-overlapping Places asset")
        boundary_path = project_root / "data/raw/astana-boundary-geometry.json"
        if not boundary_path.exists():
            response = client.get("https://nominatim.openstreetmap.org/lookup", params={"osm_ids": "R3087155", "format": "jsonv2", "polygon_geojson": "1"})
            response.raise_for_status()
            write_json(boundary_path, response.json())
    connection = duckdb.connect()
    connection.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial;")
    connection.execute("SET threads=2; SET memory_limit='1GB';")
    query = """SELECT id, names, taxonomy, basic_category, confidence,
        operating_status, websites, socials, emails, phones, brand, addresses,
        sources, version, ST_X(geometry) AS lon, ST_Y(geometry) AS lat
        FROM read_parquet(?)
        WHERE bbox.xmin BETWEEN ? AND ? AND bbox.ymin BETWEEN ? AND ?
        AND names.primary IS NOT NULL"""
    cursor = connection.execute(query, [urls, west, east, south, north])
    columns = [field[0] for field in cursor.description]
    records = [dict(zip(columns, row)) for row in cursor.fetchall()]
    records.sort(key=lambda x: x["id"])
    raw = {"metadata": {"provider": "Overture Maps Foundation", "catalog_url": CATALOG,
        "release": release, "observed_at": observed, "bbox": target,
        "query": query, "selected_asset_count": len(selected), "catalog_asset_count": len(items),
        "selected_assets": urls, "stac_catalog": catalog, "stac_collection": collection,
        "selected_stac_items": selected, "record_count": len(records),
        "method": "STAC extent filtering + GeoParquet bbox predicate pushdown; only local bbox records retained; no world download"}, "records": records}
    write_json(project_root / "data/raw/overture-astana-places.json", raw)
    return raw


def category_of(record: dict) -> tuple[str, str] | None:
    """Explicit visitor destinations. Exclude offices, services and generic POIs."""
    taxonomy = record.get("taxonomy") or {}
    kind = taxonomy.get("primary") or record.get("basic_category") or ""
    hierarchy = set(taxonomy.get("hierarchy") or []) | {kind}
    # Most-specific destinations precede the broad arts/entertainment parent.
    if kind in {"karaoke_venue", "hookah_bar", "sports_bar", "airport_lounge"}: return "nightlife", kind
    if kind in {"stadium_arena", "amusement_park", "bowling_alley", "escape_room", "water_park", "ice_skating_rink", "sports_center", "swimming_pool"}: return "sport", kind
    if hierarchy & {"coffee_shop", "cafe", "tea_room", "tea_house"}: return "cafe", kind
    if hierarchy & {"restaurant", "fast_food_restaurant", "ice_cream_shop", "food_court", "bakery", "dessert_shop"}: return "dining", kind
    if hierarchy & {"bar", "pub", "nightclub", "cocktail_bar", "brewery", "lounge"}: return "nightlife", kind
    if hierarchy & {"museum", "art_museum", "history_museum", "science_museum"}: return "museum", kind
    if hierarchy & {"art_gallery", "performing_arts", "theater", "theatre", "cinema", "movie_theater", "library", "cultural_center", "arts_and_entertainment", "music_venue", "concert_hall", "opera_house", "planetarium", "historical_site", "monument", "landmark", "tourist_attraction"}: return "culture", kind
    if hierarchy & {"park", "garden", "botanical_garden", "nature_reserve", "beach", "hiking_trail"}: return "park", kind
    if hierarchy & {"playground", "indoor_playcenter", "children_amusement_center"}: return "playground", kind
    if hierarchy & {"zoo", "aquarium", "amusement_park", "theme_park", "water_park", "bowling_alley", "escape_room", "ice_skating_rink", "sports_center", "swimming_pool", "stadium", "miniature_golf"}: return "sport", kind
    if hierarchy & {"shopping_mall", "shopping_center", "bookstore", "market", "farmers_market", "flea_market"}: return "shopping", kind
    if hierarchy & {"viewpoint", "scenic_lookout", "observation_deck"}: return "viewpoint", kind
    return None


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = value.replace("ё", "е").replace("&", "and")
    return "".join(c for c in value if c.isalnum())


def aliases(poi: dict) -> set[str]:
    tags = poi.get("raw_tags") or {}
    values = [poi.get("name", ""), *(poi.get("names") or {}).values(), *(poi.get("aliases") or []), *[tags.get(key, "") for key in ("alt_name", "int_name", "official_name", "short_name", "brand", "brand:en", "brand:ru")]]
    transliteration = str.maketrans({"а": "a", "ә": "a", "б": "b", "в": "v", "г": "g", "ғ": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "қ": "q", "л": "l", "м": "m", "н": "n", "ң": "ng", "о": "o", "ө": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ұ": "u", "ү": "u", "ф": "f", "х": "kh", "һ": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "і": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya"})
    normalized = {normalize_name(v) for v in values if isinstance(v, str) and len(normalize_name(v)) >= 3}
    generic = {"cafe", "кафе", "кофейня", "coffee", "coffees", "restaurant", "ресторан", "restobar", "рестобар", "bar", "бар", "pub", "паб", "grill", "гриль", "karaoke", "караоке", "astana", "астана", "нурсултан", "nursultan", "park", "парк", "arena", "арена", "shopping", "mall", "center", "центр", "кафесі", "мейрамхана"}
    for value in values:
        if not isinstance(value, str): continue
        tokens = re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", value.casefold()))
        distinctive = [word for word in tokens if word not in generic]
        if distinctive and len("".join(distinctive)) >= 4:
            normalized.add(normalize_name(" ".join(distinctive)))
    return normalized | {v.translate(transliteration) for v in normalized}


def distance(a: dict, b: dict) -> float:
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dl, dp = math.radians(b["lon"] - a["lon"]), p2 - p1
    return 6371000 * 2 * math.asin(min(1, math.sqrt(math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)))


def phone_key(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")[-10:]


def site_key(value: str | None) -> str:
    if not value: return ""
    parsed = urlparse(value if "://" in value else "https://" + value)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    # Aggregator/social links or chain homepages do not identify a branch.
    return (host + parsed.path.rstrip("/")).casefold() if parsed.path not in {"", "/"} and host not in {"facebook.com", "instagram.com", "vk.com", "t.me"} else ""


def source_for(record: dict, raw: dict) -> dict:
    sources = record.get("sources") or []
    licenses = sorted({source["license"] for source in sources if source.get("license")})
    return {"name": "Overture Maps", "url": "https://explore.overturemaps.org/?id=" + record["id"],
        "collected_at": raw["metadata"]["observed_at"], "release": raw["metadata"]["release"],
        "gers_id": record["id"], "version": record.get("version"), "confidence": record.get("confidence"),
        "licenses": licenses, "license_urls": [LICENSES[x] for x in licenses if x in LICENSES],
        "attribution": "Overture Maps Foundation; " + "; ".join(sorted({source.get("dataset", "") for source in sources})),
        "original_sources": deepcopy(sources), "schema_url": "https://docs.overturemaps.org/schema/reference/places/place/"}


def normalize_record(record: dict, raw: dict, category: str, kind: str) -> dict:
    name = (record["names"]["primary"] or "").strip()
    names = {"en": name, "ru": name, "kk": name}
    for lang, item in (record["names"].get("common") or {}).items():
        if lang in names and item: names[lang] = item[0] if isinstance(item, list) else item
    phone = next(iter(record.get("phones") or []), None)
    website = next(iter(record.get("websites") or []), None)
    address = next(iter(record.get("addresses") or []), {})
    address_text = address.get("freeform") or ", ".join(str(address[k]) for k in ("locality", "region", "postcode", "country") if address.get(k)) or None
    indoors = category in {"cafe", "dining", "nightlife", "museum", "shopping"}
    tags = {category, kind}
    if indoors: tags.add("indoors")
    if category in {"park", "playground"}: tags.update({"outdoors", "walk", "nature", "family"})
    if category in {"culture", "museum", "viewpoint"}: tags.update({"culture", "explore"})
    return {"id": "overture-" + record["id"], "name": name, "name_derived": False,
        "names": names, "aliases": sorted({name, *[v for v in names.values()]}),
        "lat": record["lat"], "lon": record["lon"], "category": category, "poi_type": kind,
        "description": f'{kind.replace("_", " ").capitalize()} listed in Astana by Overture Maps source contributors.',
        "description_source": None, "description_derived": True, "tags": sorted(tags),
        "hours": None, "rating": None, "rating_count": None, "rating_source": None,
        "reviews": [], "review_count": None, "photos": [], "image": None,
        "wheelchair": "unknown", "indoor": indoors, "indoor_evidence": "category-inference",
        "phone": phone, "website": website, "address": address_text,
        "contact": {"phone": phone, "website": website, "email": next(iter(record.get("emails") or []), None)},
        "amenities": {}, "accessibility": {"wheelchair": "unknown"}, "wikidata": None,
        "wikipedia": None, "source": source_for(record, raw), "raw_tags": {},
        "duplicate_source_ids": [], "coordinates_note": "Overture source point; entrance and walkable access are not verified",
        "operating_status": record.get("operating_status"), "existence_confidence": record.get("confidence"),
        "recommendable": True}


def merge_overture(dataset: dict, raw: dict, boundary: dict) -> tuple[dict, dict]:
    """Retain existing public facts; add conservative matches as secondary proof."""
    boundary_covers(boundary, 71.43, 51.13)  # Validate geometry before any merge.
    result = deepcopy(dataset)
    all_pois = result["pois"]
    existing = {poi["id"]: poi for poi in all_pois}
    linked_gers = {source["gers_id"]: poi["id"] for poi in all_pois for source in poi.get("additional_sources", []) if source.get("gers_id")}
    spatial: dict[tuple[int, int], list[dict]] = {}
    def index(poi):
        spatial.setdefault((int(poi["lat"] * 500), int(poi["lon"] * 500)), []).append(poi)
    for poi in all_pois: index(poi)
    decisions = []
    from collections import Counter
    # Repeated unrelated names on one metre-scale coordinate are commonly a
    # locality centroid. Existence confidence does not establish geocode quality.
    collapsed = Counter((round(r.get("lat", 0), 5), round(r.get("lon", 0), 5)) for r in raw["records"])
    for record in sorted(raw["records"], key=lambda x: (-float(x.get("confidence") or 0), x["id"])):
        identity = "overture-" + record["id"]
        decision = {"gers_id": record["id"], "name": (record.get("names") or {}).get("primary"), "confidence": record.get("confidence")}
        def reject(reason): decisions.append({**decision, "decision": "excluded", "reason": reason})
        if identity in existing:
            decisions.append({**decision, "decision": "existing", "poi_id": identity}); continue
        if record["id"] in linked_gers:
            decisions.append({**decision, "decision": "existing-match", "poi_id": linked_gers[record["id"]]}); continue
        category = category_of(record)
        if not category: reject("not-an-explicit-visitor-destination"); continue
        if record.get("confidence") is None or record["confidence"] < MIN_CONFIDENCE: reject("existence-confidence-below-0.85"); continue
        if record.get("operating_status") in {"permanently_closed", "temporarily_closed"}: reject("source-reports-closed"); continue
        if not all(isinstance(record.get(k), (float, int)) and math.isfinite(record[k]) for k in ("lat", "lon")): reject("invalid-coordinates"); continue
        if not boundary_covers(boundary, record["lon"], record["lat"]): reject("outside-Astana-administrative-polygon"); continue
        if collapsed[(round(record["lat"], 5), round(record["lon"], 5))] >= 5: reject("collapsed-multi-business-coordinate"); continue
        name = (record.get("names") or {}).get("primary", "").strip()
        if len(normalize_name(name)) < 3 or re.search(r"https?://|\\[nr]|@", name): reject("invalid-venue-name"); continue
        licenses = {x.get("license") for x in record.get("sources", []) if x.get("license")}
        if not licenses or not licenses <= set(LICENSES): reject("missing-or-unreviewed-license"); continue
        candidate = normalize_record(record, raw, *category)
        nearby = []
        cell = (int(candidate["lat"] * 500), int(candidate["lon"] * 500))
        for dy in range(-1, 2):
            for dx in range(-2, 3):
                nearby.extend(spatial.get((cell[0] + dy, cell[1] + dx), []))
        matches, uncertain = [], []
        for poi in nearby:
            meters = distance(candidate, poi)
            if meters > 180: continue
            names_a, names_b = aliases(candidate), aliases(poi)
            exact = bool(names_a & names_b)
            similarity = max((SequenceMatcher(None, a, b).ratio() for a in names_a for b in names_b), default=0)
            same_category = poi["category"] == candidate["category"]
            same_phone = len(phone_key(candidate.get("phone"))) >= 9 and phone_key(candidate.get("phone")) == phone_key(poi.get("phone"))
            same_site = bool(site_key(candidate.get("website"))) and site_key(candidate.get("website")) == site_key(poi.get("website"))
            if (exact and meters <= 45) or (same_category and ((exact and meters <= 90) or (similarity >= .92 and meters <= 45) or ((same_phone or same_site) and similarity >= .65 and meters <= 120))):
                matches.append((meters, poi, exact, similarity))
            elif (exact and meters <= 180) or (same_category and similarity >= .7 and meters <= 120):
                uncertain.append((meters, poi, similarity))
        if len(matches) == 1:
            meters, target, exact, similarity = matches[0]
            target.setdefault("additional_sources", []).append(candidate["source"])
            target["aliases"] = sorted(set(target.get("aliases", [])) | {candidate["name"]})
            # Keep known facts/coordinates intact; differing contacts are audit
            # conflicts, not silently chosen replacements.
            conflicts = {key: {"retained": target.get(key), "candidate": candidate.get(key)} for key in ("phone", "website", "address") if target.get(key) and candidate.get(key) and target[key] != candidate[key]}
            decisions.append({**decision, "decision": "matched", "poi_id": target["id"], "distance_m": round(meters, 2), "exact_normalized_name": exact, "name_similarity": round(similarity, 4), "contact_conflicts": conflicts})
        elif matches or uncertain:
            possible = [{"poi_id": x[1]["id"], "distance_m": round(x[0], 2)} for x in matches + uncertain]
            decisions.append({**decision, "decision": "quarantined", "reason": "ambiguous-nearby-identity", "possible_matches": possible})
        else:
            all_pois.append(candidate); existing[identity] = candidate; index(candidate)
            decisions.append({**decision, "decision": "added", "poi_id": identity, "category": candidate["category"]})
    all_pois.sort(key=lambda x: x["id"])
    report = {"collected_at": raw["metadata"]["observed_at"], "release": raw["metadata"]["release"],
        "before": coverage(dataset["pois"]), "after": coverage(all_pois),
        "decisions": dict(Counter(d["decision"] for d in decisions)),
        "excluded_reasons": dict(Counter(d["reason"] for d in decisions if d["decision"] == "excluded")),
        "minimum_existence_confidence": MIN_CONFIDENCE, "records": decisions,
        "policy": "Preserve existing IDs, coordinates and facts; named explicit visitor destinations only; exact city polygon; similarity+distance+category or branch contact; ambiguous identity quarantined; no guessed hours, ratings, accessibility or photos"}
    result["metadata"].update(count=len(all_pois), coverage=coverage(all_pois))
    result["metadata"]["scope"] = "Astana administrative boundary; OSM inventory plus filtered licensed Overture visitor destinations"
    result["metadata"]["attribution"] = "© OpenStreetMap contributors; Overture Maps Foundation and source contributors"
    result["metadata"]["notes"] = "Citywide mapped OSM inventory with filtered licensed Overture visitor destinations, not a census of all physical establishments. Per-source identities, release dates and license notices are retained. Provider existence confidence is not a rating, current-hours check or coordinate-accuracy guarantee. Ambiguous identities and collapsed coordinates are excluded. Unknown hours, ratings, reviews, photos and accessibility stay unknown. No Google, Yandex or 2GIS content is scraped."
    result["metadata"]["additional_collections"] = [{"provider": "Overture Maps", "release": raw["metadata"]["release"], "collected_at": raw["metadata"]["observed_at"], "raw_path": "data/raw/overture-astana-places.json", "raw_sha256": hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest(), "decisions": report["decisions"], "licenses": LICENSES, "attribution_url": "https://docs.overturemaps.org/attribution/", "notes": "Existence confidence is not a rating, quality measure or current opening status. No source photographs or reviews are implied."}]
    return result, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect", action="store_true", help="Collect spatially selective live Overture records")
    parser.add_argument("--input", type=Path, default=ROOT / "data/pois.json")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/data-expansion-staging/pois-expanded.json")
    args = parser.parse_args()
    raw = collect() if args.collect else json.loads((ROOT / "data/raw/overture-astana-places.json").read_text())
    candidate, report = merge_overture(json.loads(args.input.read_text()), raw, json.loads((ROOT / "data/raw/astana-boundary-geometry.json").read_text()))
    write_json(args.output, candidate)
    write_json(ROOT / "data/raw/overture-entity-resolution.json", report)
    print(json.dumps({"before": report["before"]["total"], "after": report["after"]["total"], "decisions": report["decisions"], "excluded_reasons": report["excluded_reasons"], "output": str(args.output)}))


if __name__ == "__main__": main()
