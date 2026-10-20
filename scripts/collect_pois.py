#!/usr/bin/env python3
"""Collect real Astana POIs from Overpass, retaining provenance and raw source.

Run: uv run python scripts/collect_pois.py
No credentials; retries public mirrors. Never fills unknown hours or ratings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
# Astana's city-of-republican-significance boundary, verified against the live
# Nominatim relation and Overpass relation tags. This covers the entire city,
# including its airport and outer residential districts, not a downtown rectangle.
BOUNDARY_RELATION = 3087155
BOUNDARY_AREA = 3600000000 + BOUNDARY_RELATION
BOUNDARY_BBOX = [50.8576076, 71.2179735, 51.3511101, 71.7851913]
QUERY = f'''[out:json][timeout:180];
area({BOUNDARY_AREA})->.city;
(
 nwr["amenity"](area.city);
 nwr["shop"](area.city);
 nwr["tourism"](area.city);
 nwr["leisure"](area.city);
 nwr["historic"](area.city);
 nwr["natural"~"^(beach|wood|water)$"](area.city);
 nwr["railway"="station"](area.city);
 nwr["aeroway"="aerodrome"](area.city);
);
out meta center;'''
MIRRORS = ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
USER_AGENT = "QalaResearch/2.0 (Astana walking companion; reproducible open POI dataset)"

TOURISM = {"museum", "attraction", "artwork", "gallery", "viewpoint", "zoo", "aquarium", "theme_park", "picnic_site", "information", "hotel", "hostel", "guest_house", "motel", "camp_site"}
LEISURE = {"park", "garden", "playground", "nature_reserve", "dog_park", "sports_centre", "fitness_centre", "sports_hall", "swimming_pool", "water_park", "ice_rink", "stadium", "pitch", "track", "fitness_station", "bowling_alley", "miniature_golf", "amusement_arcade", "escape_game", "dance", "beach_resort", "outdoor_seating"}
CULTURE_AMENITIES = {"arts_centre", "theatre", "library", "cinema", "community_centre", "exhibition_centre", "planetarium", "place_of_worship", "events_venue", "music_venue", "fountain"}
UTILITY_AMENITIES = {"toilets", "drinking_water", "shelter", "bench", "pharmacy", "hospital", "clinic", "doctors", "police", "bank", "atm", "post_office", "marketplace", "bicycle_rental", "bicycle_repair_station", "charging_station", "parking", "fuel"}
AMENITIES = CULTURE_AMENITIES | UTILITY_AMENITIES | {"cafe", "restaurant", "fast_food", "food_court", "ice_cream", "bar", "pub", "nightclub", "biergarten", "bus_station", "ferry_terminal"}
HISTORIC = {"monument", "memorial", "castle", "ruins", "archaeological_site", "building", "heritage", "tomb"}
UNNAMED_PUBLIC = {"park", "garden", "playground", "nature_reserve", "dog_park", "picnic_site", "fitness_station", "pitch", "track", "toilets", "drinking_water", "shelter", "bench", "fountain", "bicycle_rental", "bicycle_repair_station", "viewpoint", "artwork"}



def enrich_official(dataset: dict, offline_sources: dict | None = None) -> None:
    """Small, auditable operator allowlist. Facts only apply after live checks.

    OSM remains the coordinate/source authority; each operator fact carries a
    separate URL and observed timestamp. HTML snapshots support audit/replay.
    """
    official = [("osm-node-4894937300", "https://www.nmrk.kz/en/", "national-museum"),
                ("osm-way-230401645", "https://a-vm.kz/en/objects/bayterek/", "baiterek")]
    enriched, failures = 0, []
    for poi_id, url, slug in official:
        target = next((p for p in dataset["pois"] if p["id"] == poi_id), None)
        if not target:
            continue
        try:
            if offline_sources is None:
                res = httpx.get(url, timeout=15, follow_redirects=True)
                res.raise_for_status()
                source_html = res.text
                observed = datetime.now(timezone.utc).isoformat()
            else:
                source_html = offline_sources[url]["html"]
                observed = offline_sources[url]["observed_at"]
            plain = re.sub(r"<[^>]+>", " ", source_html)
            plain = " ".join(plain.split())
            fact_source = {"name": "Venue operator", "url": url, "collected_at": observed}
            if slug == "national-museum" and "Monday is a day off" in plain and re.search(r"10:00\s*[-–]\s*18:00\s*Tue-Sun", plain):
                target["hours"] = "Tu-Su 10:00-18:00"
                target["description"] = "National Museum of the Republic of Kazakhstan, at Tauelsizdik Avenue 54. The operator lists Tuesday–Sunday visitor hours; Monday is a day off."
                target["hours_source"] = fact_source
                target["description_source"] = fact_source
            elif slug == "baiterek" and "September 1" in plain and "9:00 PM" in plain and "10:00 PM" in plain:
                target["hours"] = "10:00-21:00"
                target["seasonal_hours"] = {"summer_months": [6, 7, 8], "summer": "10:00-22:00", "other": "10:00-21:00"}
                target["description"] = "Baiterek is a 105-metre monument in Astana, completed in 2002. Its operator publishes seasonal visiting hours."
                target["hours_source"] = fact_source
                target["description_source"] = fact_source
            else:
                failures.append(f"{slug}: expected operator facts not found; OSM unchanged")
                continue
            target["website"] = url
            target["description_derived"] = False
            target.setdefault("contact", {})["website"] = url
            snapshot = ROOT / "data/raw" / f"{slug}-operator.html"
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            if offline_sources is None:
                snapshot.write_text(source_html)
            enriched += 1
        except (httpx.HTTPError, ValueError):
            failures.append(f"{slug}: operator fetch failed; OSM unchanged")
    dataset["metadata"]["operator_enrichment"] = {"count": enriched, "failures": failures}
    dataset["metadata"]["coverage"] = coverage(dataset["pois"])


def classify(tags: dict) -> str:
    """Keep exact cafe semantics; broad inventory does not turn bars into cafes."""
    amenity, tourism, leisure = (tags.get(k) for k in ("amenity", "tourism", "leisure"))
    if amenity == "cafe": return "cafe"
    if amenity in {"restaurant", "fast_food", "food_court", "ice_cream"}: return "dining"
    if amenity in {"bar", "pub", "nightclub", "biergarten"}: return "nightlife"
    if tags.get("shop") or amenity == "marketplace": return "shopping"
    if leisure == "playground": return "playground"
    if leisure in {"park", "garden", "nature_reserve", "dog_park"} or tourism == "picnic_site" or tags.get("natural") in {"beach", "wood", "water"}: return "park"
    if tourism == "museum": return "museum"
    if tourism == "viewpoint": return "viewpoint"
    if tourism in {"hotel", "hostel", "guest_house", "motel", "camp_site"}: return "accommodation"
    if tags.get("railway") == "station" or tags.get("aeroway") == "aerodrome" or amenity in {"bus_station", "ferry_terminal"}: return "transport"
    if amenity in UTILITY_AMENITIES or leisure == "outdoor_seating": return "utility"
    if leisure and leisure not in {"park", "garden", "nature_reserve", "dog_park", "playground"}: return "sport"
    return "culture"


def poi_type(tags: dict) -> str:
    return next((tags[k] for k in ("amenity", "tourism", "leisure", "shop", "historic", "natural", "railway", "aeroway") if tags.get(k)), "point_of_interest")


def is_in_scope(tags: dict) -> bool:
    # Whole-value matching prevents e.g. internet_cafe from becoming a café.
    return (tags.get("tourism") in TOURISM or tags.get("leisure") in LEISURE
            or tags.get("amenity") in AMENITIES or tags.get("historic") in HISTORIC
            or (bool(tags.get("shop")) and tags["shop"] not in {"vacant", "no"})
            or tags.get("natural") in {"beach", "wood", "water"}
            or tags.get("railway") == "station" or tags.get("aeroway") == "aerodrome")


def coverage(pois: list[dict]) -> dict:
    from collections import Counter
    return {
        "total": len(pois), "named": sum(not p.get("name_derived", False) for p in pois),
        "by_category": dict(sorted(Counter(p["category"] for p in pois).items())),
        "with_hours": sum(bool(p.get("hours")) for p in pois),
        "with_description_from_source": sum(bool(p.get("description_source")) for p in pois),
        "wheelchair_yes": sum(p["wheelchair"] == "yes" for p in pois),
        "wheelchair_limited": sum(p["wheelchair"] == "limited" for p in pois),
        "wheelchair_no": sum(p["wheelchair"] == "no" for p in pois),
        "wheelchair_unknown": sum(p["wheelchair"] not in {"yes", "limited", "no"} for p in pois),
        "with_website": sum(bool(p.get("website")) for p in pois),
        "with_phone": sum(bool(p.get("phone")) for p in pois),
        "with_address": sum(bool(p.get("address")) for p in pois),
        "with_photos": sum(bool(p.get("photos")) for p in pois),
        "photo_count": sum(len(p.get("photos", [])) for p in pois),
        "with_wikidata": sum(bool(p.get("wikidata")) for p in pois),
        "with_wikipedia": sum(bool(p.get("wikipedia")) for p in pois),
        "rating_available": sum(p.get("rating") is not None for p in pois),
        "with_reviews": sum(bool(p.get("reviews")) for p in pois),
        "power_supply_known": sum(p.get("amenities", {}).get("power_supply") is not None for p in pois),
    }


def transform(raw: dict, endpoint: str, collected: str) -> dict:
    pois, seen_ids, seen_places = [], set(), {}
    discarded = {"out_of_scope": 0, "unnamed_non_public": 0, "invalid_coordinates": 0, "duplicate": 0, "inactive": 0}
    for el in raw.get("elements", []):
        tags = el.get("tags", {})
        if not is_in_scope(tags):
            discarded["out_of_scope"] += 1; continue
        if any(tags.get(k) == "yes" for k in ("disused", "abandoned", "demolished", "construction")):
            discarded["inactive"] += 1; continue
        point = el if "lat" in el else el.get("center", {})
        if not isinstance(point.get("lat"), (float, int)) or not isinstance(point.get("lon"), (float, int)) or not (-90 <= point["lat"] <= 90 and -180 <= point["lon"] <= 180):
            discarded["invalid_coordinates"] += 1; continue
        kind = poi_type(tags)
        original_name = tags.get("name") or tags.get("name:en") or tags.get("name:ru") or tags.get("name:kk")
        if not original_name and kind not in UNNAMED_PUBLIC:
            discarded["unnamed_non_public"] += 1; continue
        name = tags.get("name:en") or original_name or kind.replace("_", " ").capitalize()
        identity = f'osm-{el["type"]}-{el["id"]}'
        key = (name.casefold(), kind, round(point["lat"], 4), round(point["lon"], 4))
        # Never collapse distinct unnamed benches/playgrounds or adjacent branches.
        if identity in seen_ids or (original_name and key in seen_places):
            discarded["duplicate"] += 1
            if original_name and key in seen_places:
                seen_places[key]["duplicate_source_ids"].append(identity)
            continue
        seen_ids.add(identity)
        category = classify(tags)
        semantic = [category, kind]
        if category in {"park", "playground"}: semantic += ["outdoors", "walk", "nature", "family"]
        if category in {"culture", "museum", "viewpoint"}: semantic += ["culture", "explore"]
        if tags.get("historic") in {"monument", "memorial"} or category == "viewpoint": semantic += ["photography"]
        indoor = tags.get("indoor") == "yes" or (tags.get("indoor") != "no" and category in {"museum", "shopping", "cafe", "dining", "nightlife", "accommodation"})
        if indoor: semantic += ["indoors"]
        if tags.get("internet_access") in {"wlan", "yes"}: semantic += ["wifi"]
        if tags.get("socket") == "yes" or tags.get("power_supply") not in {None, "no"}: semantic += ["power"]
        if tags.get("wheelchair") == "yes": semantic += ["wheelchair"]
        if tags.get("outdoor_seating") == "yes": semantic += ["terrace"]
        if tags.get("access") in {"private", "no"}: semantic += ["restricted_access"]
        source = {"name": "OpenStreetMap", "url": f'https://www.openstreetmap.org/{el["type"]}/{el["id"]}', "collected_at": collected, "updated_at": el.get("timestamp"), "element_type": el["type"], "element_id": el["id"], "version": el.get("version")}
        description = tags.get("description:en") or tags.get("description")
        address = ", ".join(filter(None, [" ".join(filter(None, [tags.get("addr:street"), tags.get("addr:housenumber")])), tags.get("addr:suburb"), tags.get("addr:city")])) or None
        phone, website = tags.get("phone") or tags.get("contact:phone"), tags.get("website") or tags.get("contact:website")
        poi = {"id": identity, "name": name, "name_derived": not bool(original_name),
               "names": {"en": tags.get("name:en", original_name or name), "ru": tags.get("name:ru", original_name or name), "kk": tags.get("name:kk", original_name or name)},
               "lat": point["lat"], "lon": point["lon"], "category": category, "poi_type": kind,
               "description": description or f'{kind.replace("_", " ").capitalize()} mapped in Astana by OpenStreetMap contributors.',
               "description_source": source if description else None, "description_derived": not bool(description),
               "tags": sorted(set(semantic)), "hours": tags.get("opening_hours"), "rating": None,
               "rating_count": None, "rating_source": None, "reviews": [], "review_count": None,
               "photos": [], "image": None, "wheelchair": tags.get("wheelchair", "unknown"), "indoor": indoor,
               "indoor_evidence": "source-tag" if tags.get("indoor") in {"yes", "no"} else "category-inference",
               "phone": phone, "website": website, "address": address,
               "contact": {"phone": phone, "website": website, "email": tags.get("email") or tags.get("contact:email")},
               "amenities": {k.replace(":", "_"): tags.get(k) for k in ("internet_access", "power_supply", "outdoor_seating", "toilets", "toilets:wheelchair", "drinking_water", "fee", "access", "lit", "surface")},
               "accessibility": {"wheelchair": tags.get("wheelchair", "unknown"), **{k.replace(":", "_"): tags.get(k) for k in ("wheelchair:description", "entrance", "step_count", "tactile_paving", "hearing_loop")}},
               "wikidata": tags.get("wikidata"), "wikipedia": tags.get("wikipedia"),
               "source": source, "raw_tags": tags, "duplicate_source_ids": [],
               "coordinates_note": "OSM mapped point" if "lat" in el else "OSM bounding-box center; entrance may differ",
               "recommendable": category not in {"utility", "transport", "accommodation"} and tags.get("access") not in {"private", "no"}}
        pois.append(poi)
        if original_name: seen_places[key] = poi
    pois.sort(key=lambda p: p["id"])
    return {"metadata": {"city": "Astana", "scope": "Full OpenStreetMap Astana administrative boundary", "boundary_relation": BOUNDARY_RELATION, "boundary_url": f"https://www.openstreetmap.org/relation/{BOUNDARY_RELATION}", "bbox": BOUNDARY_BBOX, "collected_at": collected, "osm_base_timestamp": raw.get("osm3s", {}).get("timestamp_osm_base"), "endpoint": endpoint, "count": len(pois), "raw_element_count": len(raw.get("elements", [])), "discarded": discarded, "coverage": coverage(pois), "license": "ODbL 1.0", "attribution": "© OpenStreetMap contributors", "license_url": "https://www.openstreetmap.org/copyright", "query": QUERY, "raw_sha256": hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest(), "notes": "Citywide OSM snapshot, not an exhaustive census of physical places. Category descriptions and interest tags are derived. Unknown hours, ratings, reviews and accessibility stay unknown. Area coordinates may be centers. Exactlinked Wikimedia photos have individual licenses. No Google or 2GIS data is scraped."}, "pois": pois}


def fetch_overpass(query: str, mirrors: list[str] = MIRRORS) -> tuple[dict, str]:
    errors = []
    with httpx.Client(timeout=210, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        for endpoint in mirrors:
            for method in ("POST", "GET"):
                try:
                    res = client.post(endpoint, data={"data": query}) if method == "POST" else client.get(endpoint, params={"data": query})
                    res.raise_for_status()
                    raw = res.json()
                    if raw.get("remark") or not raw.get("elements"):
                        raise ValueError("Incomplete or empty Overpass response")
                    return raw, endpoint
                except (httpx.HTTPError, ValueError) as exc:
                    errors.append(f"{endpoint} {method}: {type(exc).__name__}")
    raise RuntimeError("Collection failed; existing dataset preserved. " + "; ".join(errors))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Reprocess a previously collected raw OSM response")
    parser.add_argument("--output", type=Path, default=ROOT / "data/pois.json")
    parser.add_argument("--skip-operator", action="store_true", help="Offline replay only; skip live operator verification")
    parser.add_argument("--photos", action="store_true", help="Enrich exact-linked Wikimedia/Wikidata photographs with license metadata")
    args = parser.parse_args()
    collected = datetime.now(timezone.utc).isoformat()
    raw, endpoint = (json.loads(args.input.read_text()), "local raw snapshot") if args.input else fetch_overpass(QUERY)
    if not args.input: write_json(ROOT / "data/raw/astana-overpass-citywide.json", raw)
    dataset = transform(raw, endpoint, collected)
    if not args.skip_operator: enrich_official(dataset)
    if len(dataset["pois"]) < 10: raise SystemExit("Too few valid POIs; existing dataset preserved")
    if args.photos:
        from enrich_poi_media import enrich_media
        enrich_media(dataset)
    dataset["metadata"]["coverage"] = coverage(dataset["pois"])
    write_json(args.output, dataset)
    print(f'Collected {len(dataset["pois"])} genuine POIs → {args.output}')
    print(json.dumps(dataset["metadata"]["coverage"], ensure_ascii=False))


if __name__ == "__main__": main()
