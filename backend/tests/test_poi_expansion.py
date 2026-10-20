"""Public-source conflation boundaries; never contact live providers."""
from copy import deepcopy

import pytest

from scripts.collect_overture_places import boundary_covers, category_of, merge_overture
from scripts.collect_pois import transform
from scripts.export_poi_dataset import validate_dataset


BOUNDARY = {"geojson": {"type": "Polygon", "coordinates": [[[71.2, 50.8], [71.8, 50.8], [71.8, 51.4], [71.2, 51.4], [71.2, 50.8]], [[71.6, 51.2], [71.7, 51.2], [71.7, 51.3], [71.6, 51.3], [71.6, 51.2]]]}}


def baseline():
    return transform({"elements": [{"type": "node", "id": 1, "lat": 51.1, "lon": 71.4, "tags": {"name": "Коктем", "amenity": "cafe", "opening_hours": "Mo-Fr 09:00-18:00", "phone": "+77111111111"}}]}, "fixture", "2026-10-20T00:00:00Z")


def record(number=1, name="Different Coffee", **changes):
    return {"id": f"00000000-0000-0000-0000-{number:012d}", "names": {"primary": name}, "taxonomy": {"primary": "coffee_shop", "hierarchy": ["food_and_drink", "coffee_shop"]}, "confidence": .95, "operating_status": None, "lat": 51.12, "lon": 71.42, "sources": [{"dataset": "meta", "license": "CDLA-Permissive-2.0", "record_id": str(number)}], **changes}


def raw(*records):
    return {"metadata": {"observed_at": "2026-10-20T00:00:00Z", "release": "2026-09-23.1"}, "records": list(records)}


def test_polygon_filter_includes_city_and_excludes_holes_and_surrounding_bbox():
    assert boundary_covers(BOUNDARY, 71.4, 51.1)
    assert boundary_covers(BOUNDARY, 71.2, 51.1)
    assert not boundary_covers(BOUNDARY, 71.65, 51.25)
    assert not boundary_covers(BOUNDARY, 71.9, 51.1)
    with pytest.raises(ValueError):
        boundary_covers({"geojson": {"type": "Point", "coordinates": [71.4, 51.1]}}, 71.4, 51.1)


@pytest.mark.parametrize("changes,reason", [
    ({"confidence": .84}, "existence-confidence-below-0.85"),
    ({"operating_status": "permanently_closed"}, "source-reports-closed"),
    ({"operating_status": "temporarily_closed"}, "source-reports-closed"),
    ({"sources": [{"license": "proprietary"}]}, "missing-or-unreviewed-license"),
    ({"lat": 51.25, "lon": 71.65}, "outside-Astana-administrative-polygon"),
])
def test_suspect_places_are_not_published(changes, reason):
    result, audit = merge_overture(baseline(), raw(record(**changes)), BOUNDARY)
    assert len(result["pois"]) == 1
    assert audit["excluded_reasons"] == {reason: 1}


def test_exact_transliterated_match_preserves_every_known_osm_fact_and_records_conflict():
    original = baseline()
    result, audit = merge_overture(original, raw(record(name="Koktem", lat=51.10001, lon=71.40001, phones=["+77222222222"])), BOUNDARY)
    retained = result["pois"][0]
    assert audit["decisions"] == {"matched": 1}
    assert {k: retained[k] for k in original["pois"][0]} == original["pois"][0]
    assert retained["additional_sources"][0]["gers_id"].endswith("000000000001")
    assert audit["records"][0]["contact_conflicts"]["phone"]["retained"] == "+77111111111"
    assert original["pois"][0].get("additional_sources") is None


def test_new_licensed_place_never_turns_confidence_or_operating_status_into_rating_or_hours():
    result, audit = merge_overture(baseline(), raw(record(operating_status="open")), BOUNDARY)
    new = next(p for p in result["pois"] if p["id"].startswith("overture-"))
    assert audit["decisions"] == {"added": 1}
    assert new["rating"] is None and new["hours"] is None and new["wheelchair"] == "unknown"
    assert new["photos"] == [] and new["reviews"] == []
    assert new["existence_confidence"] == .95
    assert all(validate_dataset(result).values())


def test_collapsed_generic_locality_coordinate_is_quarantined_even_with_high_confidence():
    result, audit = merge_overture(baseline(), raw(*(record(n, name=f"Place {n}") for n in range(1, 6))), BOUNDARY)
    assert len(result["pois"]) == 1
    assert audit["excluded_reasons"] == {"collapsed-multi-business-coordinate": 5}


def test_ambiguous_nearby_brand_is_quarantined_instead_of_adding_a_duplicate():
    source = baseline()
    source["pois"][0]["name"] = "Fountain House"
    source["pois"][0]["names"] = {"en": "Fountain House"}
    result, audit = merge_overture(source, raw(record(name="Fountain House Garden", lat=51.10002, lon=71.40002)), BOUNDARY)
    assert len(result["pois"]) == 1
    assert audit["decisions"] == {"quarantined": 1}


def test_repeat_merge_does_not_duplicate_primary_records_or_secondary_evidence():
    records = raw(record(name="Koktem", lat=51.10001, lon=71.40001), record(2))
    once, _ = merge_overture(baseline(), records, BOUNDARY)
    twice, audit = merge_overture(once, records, BOUNDARY)
    assert twice["pois"] == once["pois"]
    assert audit["decisions"] == {"existing-match": 1, "existing": 1}


def test_specific_sport_and_nightlife_categories_precede_arts_parent():
    assert category_of(record(taxonomy={"primary": "karaoke_venue", "hierarchy": ["arts_and_entertainment", "karaoke_venue"]}))[0] == "nightlife"
    assert category_of(record(taxonomy={"primary": "stadium_arena", "hierarchy": ["arts_and_entertainment", "stadium_arena"]}))[0] == "sport"
    assert category_of(record(taxonomy={"primary": "real_estate_service", "hierarchy": ["services_and_business"]})) is None


def test_forged_non_osm_source_identity_is_rejected():
    result, _ = merge_overture(baseline(), raw(record()), BOUNDARY)
    forged = deepcopy(result)
    next(p for p in forged["pois"] if p["id"].startswith("overture-"))["source"]["gers_id"] = "other"
    with pytest.raises(ValueError, match="Overture identity"):
        validate_dataset(forged)
