import base64
import copy
import hashlib
import json

import pytest

from scripts.collect_named_operator_venues import (
    OSM_API_URL, OSM_ID, OPERATOR_URL, VENUE_ID,
    apply_named_operator_venues, apply_retained_named_operator_venues, collect_named_operator_venue,
)
from scripts.collect_pois import transform


ACQUIRED_OSM = "2026-10-20T17:18:39.959656+00:00"
ACQUIRED_OPERATOR = "2026-10-20T17:18:25.446343+00:00"
OPENING = "The Museum of Singularity is open: 10:00-18:30 Tue–Sun, Mon — Maintenance day"


def fixtures(html=None):
    osm = {"elements": [
        {"type": "node", "id": 1, "lat": 51.089, "lon": 71.416},
        {"type": "node", "id": 2, "lat": 51.0894, "lon": 71.416},
        {"type": "node", "id": 3, "lat": 51.0892, "lon": 71.4164},
        {"type": "way", "id": OSM_ID, "version": 15, "timestamp": "2026-03-08T06:02:41Z", "nodes": [1, 2, 3, 1],
         "tags": {"name": "Alem.ai", "name:ru": "Alem.ai Международный центр искусственного интеллекта", "museum": "future", "office": "yes", "building": "office", "website": "https://alem.ai/kk/"}},
    ]}
    body = (html or f"<h1>alem.ai</h1><p>{OPENING}</p><p>[ 51.0892, 71.4161 ]</p>").encode()
    page = {"source_url": OPERATOR_URL, "final_url": OPERATOR_URL, "observed_at": ACQUIRED_OPERATOR,
            "sha256": hashlib.sha256(body).hexdigest(), "html_b64": base64.b64encode(body).decode()}
    return osm, page


def collect(osm=None, page=None):
    default_osm, default_page = fixtures()
    return collect_named_operator_venue(osm or default_osm, page or default_page,
        osm_observed_at=ACQUIRED_OSM, osm_body_sha256="a" * 64)


def dataset():
    result = transform({"elements": [{"type": "node", "id": 99, "lat": 51.089, "lon": 71.416,
        "tags": {"name": "Original historical museum", "tourism": "museum"}}]}, "fixture", ACQUIRED_OSM)
    result["pois"][0].update(id="overture-historical", operating_status="closed", recommendable=False)
    return result


def test_exact_building_identity_is_retained_and_only_museum_component_gets_hours():
    osm, page = fixtures()
    original = copy.deepcopy(osm)
    sidecar = collect(osm, page)
    poi = sidecar["candidate"]
    assert poi["id"] == VENUE_ID and poi["source"]["element_id"] == OSM_ID and poi["source"]["version"] == 15
    assert poi["source"]["collected_at"] == ACQUIRED_OSM
    assert poi["name"] == "Alem.ai"
    assert poi["names"] == {"en": "Alem.ai", "ru": original["elements"][-1]["tags"]["name:ru"], "kk": "Alem.ai"}
    assert poi["hours"] is None and "hours_source" not in poi and "operating_status" not in poi
    assert poi["category"] == "culture" and poi["poi_type"] == "architectural_landmark" and poi["recommendable"] is True
    assert poi["indoor"] is False and poi["recommended_action"] == "view_exterior"
    assert poi["tags"] == ["architecture", "culture", "outdoors", "photography", "walk"]
    assert "interior access not established" in poi["indoor_evidence"]
    component = poi["visitor_components"][0]
    assert component["name"] == "Museum of Singularity" and component["poi_type"] == "museum"
    assert component["hours"] == "Tu-Su 10:00-18:30; Mo off" and component["operating_status"] == "open"
    assert component["source"]["observed_at"] == ACQUIRED_OPERATOR
    assert "whole office centre" in component["scope"]
    assert "Museum of Singularity" not in poi["aliases"]
    assert "viewing its exterior" in poi["description"] and "inside has a separate visitor schedule" in poi["description"]
    assert poi["photos"] == [] and poi["image"] is None and poi["rating"] is None and poi["reviews"] == []
    assert poi["phone"] is None and poi["amenities"]["fee"] is None and poi["wheelchair"] == "unknown"
    assert poi["raw_tags"] == original["elements"][-1]["tags"]
    assert "tourism" not in poi["raw_tags"] and osm == original
    assert len(" ".join(sidecar["evidence"]["operator"]["excerpts"]).split()) <= 25
    assert "html_b64" not in json.dumps(sidecar)


def test_offline_apply_is_deterministic_idempotent_and_preserves_historical_closure():
    original = dataset()
    before = copy.deepcopy(original)
    sidecar = collect()
    first = apply_named_operator_venues(original, sidecar)
    assert original == before
    assert len(first["pois"]) == 2
    assert next(p for p in first["pois"] if p["id"] == "overture-historical") == before["pois"][0]
    assert apply_named_operator_venues(first, sidecar) == first
    enriched = copy.deepcopy(first)
    current = next(p for p in enriched["pois"] if p["id"] == VENUE_ID)
    current["photos"] = [{"source_url": "https://commons.wikimedia.org/wiki/File:Later-approved-photo.jpg"}]
    assert apply_named_operator_venues(enriched, sidecar)["pois"] == enriched["pois"]


@pytest.mark.parametrize("problem", ["wrong_osm_id", "wrong_domain", "wrong_name", "no_museum", "missing_node", "invalid_coordinate", "distant", "no_version", "naive_version_time"])
def test_osm_identity_or_geometry_mismatch_is_rejected(problem):
    osm, page = fixtures()
    way = osm["elements"][-1]
    if problem == "wrong_osm_id": way["id"] += 1
    elif problem == "wrong_domain": way["tags"]["website"] = "https://alem.ai.evil.example/"
    elif problem == "wrong_name": way["tags"]["name"] = "Different office"
    elif problem == "no_museum": way["tags"].pop("museum")
    elif problem == "missing_node": osm["elements"].pop(0)
    elif problem == "invalid_coordinate": osm["elements"][0]["lat"] = True
    elif problem == "distant":
        for node in osm["elements"][:-1]: node["lat"] += .01
    elif problem == "no_version": way["version"] = None
    elif problem == "naive_version_time": way["timestamp"] = "2026-03-08T06:02:41"
    with pytest.raises(ValueError): collect(osm, page)


@pytest.mark.parametrize("problem", ["wrong_domain", "wrong_redirect", "body_changed", "no_timezone", "missing_museum", "script_only", "wrong_days", "invalid_time", "missing_coords", "wrong_coords", "ambiguous_coords"])
def test_official_page_must_explicitly_establish_current_museum_location_and_hours(problem):
    html = f"<p>{OPENING}</p><p>[51.0892, 71.4161]</p>"
    if problem == "missing_museum": html = html.replace("Museum of Singularity", "Office centre")
    elif problem == "script_only": html = "<script>" + html + "</script>"
    elif problem == "wrong_days": html = html.replace("Tue–Sun", "Mon–Sun")
    elif problem == "invalid_time": html = html.replace("18:30", "28:30")
    elif problem == "missing_coords": html = html.replace("[51.0892, 71.4161]", "")
    elif problem == "wrong_coords": html = html.replace("51.0892", "51.1892")
    elif problem == "ambiguous_coords": html += "[51.1800,71.4000]"
    osm, page = fixtures(html)
    if problem == "wrong_domain": page["source_url"] = "https://alem.ai.evil.example/en/"
    elif problem == "wrong_redirect": page["final_url"] = "https://unrelated.example/en/"
    elif problem == "body_changed": page["sha256"] = "b" * 64
    elif problem == "no_timezone": page["observed_at"] = "2026-10-20T17:18:25"
    with pytest.raises(ValueError): collect(osm, page)


@pytest.mark.parametrize("problem", ["edited_candidate", "edited_excerpt", "edited_facts", "edited_osm_digest", "unknown_identity", "source_url"])
def test_retained_evidence_is_validated_before_mutating_any_dataset(problem):
    sidecar = collect()
    if problem == "edited_candidate": sidecar["candidate"]["hours"] = "24/7"
    elif problem == "edited_excerpt": sidecar["evidence"]["operator"]["excerpts"][0] += " extra"
    elif problem == "edited_facts": sidecar["evidence"]["operator"]["facts"]["hours"] = "24/7"
    elif problem == "edited_osm_digest": sidecar["evidence"]["osm"]["parsed_sha256"] = "b" * 64
    elif problem == "unknown_identity": sidecar["venue_id"] = "overture-historical"
    elif problem == "source_url": sidecar["evidence"]["osm"]["source_url"] = "https://www.openstreetmap.org/way/123"
    data = dataset(); before = copy.deepcopy(data)
    with pytest.raises(ValueError): apply_named_operator_venues(data, sidecar)
    assert data == before


def test_existing_conflicting_id_is_never_overwritten_or_silently_reopened():
    sidecar = collect()
    data = apply_named_operator_venues(dataset(), sidecar)
    next(p for p in data["pois"] if p["id"] == VENUE_ID)["recommendable"] = False
    before = copy.deepcopy(data)
    with pytest.raises(ValueError, match="conflicts"):
        apply_named_operator_venues(data, sidecar)
    assert data == before


def test_retained_helper_is_optional_and_replays_without_private_html(tmp_path):
    data = dataset()
    assert apply_retained_named_operator_venues(data, tmp_path) is data
    folder = tmp_path / "data/raw"
    folder.mkdir(parents=True)
    (folder / "named-operator-venues.json").write_text(json.dumps(collect()))
    assert len(apply_retained_named_operator_venues(data, tmp_path)["pois"]) == 2
