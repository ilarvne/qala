#!/usr/bin/env python3
"""Reconcile retained, physical Wikidata candidates without guessing identity."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import math

try:
    from scripts.collect_overture_places import aliases, boundary_covers, distance
    from scripts.collect_pois import coverage
except ModuleNotFoundError:
    from collect_overture_places import aliases, boundary_covers, distance
    from collect_pois import coverage


_NONPHYSICAL_CLASSES = {"Q4830453", "Q783794", "Q43229", "Q431289"}  # business, company, organization, brand
_CLASS_TYPES = {
    "Q16889960": "circus", "Q24354": "theatre", "Q153562": "theatre",
    "Q41253": "cinema", "Q1060829": "concert_hall", "Q7075": "library", "Q22806": "library",
    "Q33506": "museum", "Q2772772": "museum", "Q4989906": "monument", "Q860861": "monument",
    "Q32815": "mosque", "Q34627": "synagogue", "Q2977": "church", "Q56242225": "church",
    "Q2031836": "church", "Q44539": "temple", "Q22698": "park", "Q22746": "park",
    "Q167346": "park", "Q23397": "lake", "Q174782": "square", "Q12280": "bridge",
    "Q39614": "cemetery", "Q1440300": "observation_tower", "Q11315": "mall",
    "Q27686": "hotel", "Q483110": "sports_venue", "Q1154710": "sports_venue",
    "Q641226": "sports_venue", "Q1076486": "sports_venue", "Q12019965": "sports_venue",
    "Q55488": "station", "Q494829": "bus_station",
}
_POI_TYPES = {
    **{kind: kind for kind in set(_CLASS_TYPES.values())},
    "opera_house": "theatre", "cathedral": "church", "botanical_garden": "park", "urban_park": "park",
    "water": "lake", "memorial": "monument", "sculpture": "monument", "artwork": "monument",
    "stadium": "sports_venue", "arena": "sports_venue", "sports_centre": "sports_venue", "ice_rink": "sports_venue",
    "fountain": "fountain", "cafe": "commercial", "restaurant": "commercial", "fast_food": "commercial",
    "bar": "commercial", "pub": "commercial", "convenience": "commercial", "supermarket": "commercial",
}


def physical_type_compatible(poi: dict, class_ids: set[str], candidate_type: str | None = None) -> bool:
    """Reject known physical contradictions; names or explicit QIDs cannot cure them.

    Generic buildings and community/arts centres remain unspecified: a mall
    can occupy an architectural landmark, and a circus can be mapped as an
    arts centre. The primary name, coordinates and ambiguity checks still apply.
    """
    if class_ids & _NONPHYSICAL_CLASSES or candidate_type in {"business", "company", "brand", "headquarters"}:
        return False
    entity_types = {_CLASS_TYPES[qid] for qid in class_ids if qid in _CLASS_TYPES}
    if not entity_types and candidate_type in _POI_TYPES:
        entity_types.add(_POI_TYPES[candidate_type])
    if not entity_types:
        return True
    poi_type = _POI_TYPES.get(poi.get("poi_type"))
    if poi_type is None and poi.get("category") in {"cafe", "dining", "nightlife"}:
        poi_type = "commercial"
    if poi_type is None and poi.get("category") == "shopping" and poi.get("poi_type") != "mall":
        poi_type = "commercial"
    if poi_type is None:
        return True
    if poi_type in entity_types:
        return True
    # Known religious subtypes conflict, while a generic place_of_worship is
    # deliberately unspecified and therefore remains eligible for source proof.
    return False


def merge_wikidata(dataset: dict, sidecar: dict, boundary: dict | list) -> tuple[dict, dict]:
    result = deepcopy(dataset)
    pois = result["pois"]
    audit = []
    for original in sorted(sidecar.get("new_pois", []), key=lambda item: item["id"]):
        candidate = deepcopy(original)
        qid = candidate.get("wikidata")
        entry = {"poi_id": candidate.get("id"), "qid": qid, "name": candidate.get("name")}
        def reject(reason): audit.append({**entry, "decision": "quarantined", "reason": reason})
        if not qid or candidate.get("id") != "wikidata-" + qid or candidate.get("source", {}).get("url") != "https://www.wikidata.org/wiki/" + qid or candidate["source"].get("license") != "CC0" or not candidate["source"].get("p31"):
            raise ValueError("Wikidata candidate lacks typed physical source identity")
        class_ids = set(candidate["source"]["p31"])
        if not physical_type_compatible({}, class_ids, candidate.get("poi_type")):
            reject("nonphysical-organization-or-brand-identity"); continue
        if any(not isinstance(candidate.get(key), (float, int)) or not math.isfinite(candidate[key]) for key in ("lat", "lon")):
            reject("invalid-coordinates"); continue
        if not boundary_covers(boundary, candidate["lon"], candidate["lat"]):
            reject("outside-Astana-administrative-polygon"); continue
        existing = [poi for poi in pois if poi.get("wikidata") == qid]
        if len(existing) == 1:
            targets = existing
            basis = "exact-Wikidata-identity"
        elif existing:
            reject("duplicate-existing-Wikidata-identity"); continue
        else:
            names = aliases({**candidate, "aliases": candidate.get("entity_aliases", [])})
            near = [poi for poi in pois if abs(poi["lat"] - candidate["lat"]) <= .003 and abs(poi["lon"] - candidate["lon"]) <= .005 and distance(poi, candidate) <= 200]
            targets = [poi for poi in near if names & aliases(poi)]
            basis = "exact-multilingual-alias-and-distance"
        if len(targets) > 1:
            reject("ambiguous-nearby-physical-identity"); continue
        if targets:
            target = targets[0]
            if not physical_type_compatible(target, class_ids, candidate.get("poi_type")):
                reject("contradictory-physical-types"); continue
            if target.get("wikidata") and target["wikidata"] != qid:
                reject("conflicting-existing-Wikidata-identity"); continue
            if distance(target, candidate) > 2000:
                reject("source-coordinate-conflict-over-2km"); continue
            target["wikidata"] = qid
            if not any(source.get("url") == candidate["source"]["url"] for source in target.get("additional_sources", [])):
                target.setdefault("additional_sources", []).append(candidate["source"])
            target["aliases"] = sorted(set(target.get("aliases", [])) | set(candidate.get("entity_aliases", [])))
            # A linked monument photograph does not become a neighbouring café
            # photo. Exact entity identity above is required before transfer.
            known = {photo["source_url"] for photo in target.get("photos", [])}
            for photo in candidate.get("photos", []):
                if photo["source_url"] not in known:
                    target.setdefault("photos", []).append(photo); known.add(photo["source_url"])
            target["image"] = target["photos"][0]["url"] if target.get("photos") else None
            audit.append({**entry, "decision": "matched", "target_id": target["id"], "distance_m": round(distance(target, candidate), 2), "basis": basis})
            continue
        precision = candidate.get("source_p625", {}).get("precision")
        if not isinstance(precision, (float, int)) or precision <= 0 or precision > .001:
            reject("coarse-or-unknown-coordinate-precision"); continue
        # More permissive matching would risk identifying a business by the
        # adjacent building. Similar unresolved names are held out for review.
        from difflib import SequenceMatcher
        names = aliases({**candidate, "aliases": candidate.get("entity_aliases", [])})
        possible = []
        for poi in pois:
            if abs(poi["lat"] - candidate["lat"]) > .002 or abs(poi["lon"] - candidate["lon"]) > .004 or distance(poi, candidate) > 150:
                continue
            similarity = max((SequenceMatcher(None, a, b).ratio() for a in names for b in aliases(poi)), default=0)
            if poi["category"] == candidate["category"] and similarity >= .72:
                possible.append(poi["id"])
        if possible:
            audit.append({**entry, "decision": "quarantined", "reason": "unresolved-similar-nearby-name", "possible_matches": possible}); continue
        same_physical_type = []
        religious = {"mosque", "cathedral", "temple", "church", "place_of_worship"}
        for poi in pois:
            same_kind = (candidate["poi_type"] in religious and poi["poi_type"] in religious) or (candidate["category"] == "museum" and poi["category"] == "museum")
            if same_kind and abs(poi["lat"] - candidate["lat"]) <= .001 and abs(poi["lon"] - candidate["lon"]) <= .002 and distance(poi, candidate) <= 100:
                same_physical_type.append(poi["id"])
        if same_physical_type:
            audit.append({**entry, "decision": "quarantined", "reason": "nearby-same-physical-type-without-identity-proof", "possible_matches": same_physical_type}); continue
        candidate["indoor"] = candidate["category"] == "museum"
        candidate["indoor_evidence"] = "category-inference" if candidate["indoor"] else "unknown"
        if candidate.get("wikipedia"):
            lang, separator, title = candidate["wikipedia"].partition(":")
            candidate["wikipedia"] = lang.removesuffix(".json") + separator + title
        pois.append(candidate)
        audit.append({**entry, "decision": "added", "coordinate_precision_degrees": precision})
    pois.sort(key=lambda item: item["id"])
    result["metadata"].update(count=len(pois), coverage=coverage(pois))
    result["metadata"]["wikidata_collection"] = {"provider": "Wikidata / Wikipedia geographic discovery", "observed_at": sidecar["observed_at"], "license": "CC0-1.0", "source_path": "data/raw/media-upgrade-evidence.json", "decisions": dict(Counter(item["decision"] for item in audit)), "policy": "Physical P31 whitelist; exact administrative polygon; new P625 coordinate precision at most 0.001 degrees; immutable QID or exact multilingual alias plus distance; ambiguous similar names quarantined; no public-entry, current-hours, review or accessibility inference"}
    return result, {"decisions": result["metadata"]["wikidata_collection"]["decisions"], "records": audit}
