"""A physical landmark is not a nearby business or a precise geocode by default."""
from copy import deepcopy

import pytest

from scripts.collect_pois import transform
from scripts.discover_poi_media import resolve_entities
from scripts.merge_wikidata_places import merge_wikidata

BOUNDARY = {"geojson": {"type": "Polygon", "coordinates": [[[71.2, 50.8], [71.8, 50.8], [71.8, 51.4], [71.2, 51.4], [71.2, 50.8]]]}}


def baseline(kind="cafe", name="Neighbour Café", **tags):
    return transform({"elements": [{"type": "node", "id": 1, "lat": 51.1, "lon": 71.4, "tags": {"name": name, "amenity": kind, **tags}}]}, "fixture", "now")


def candidate(name="Old Trade House", **fields):
    model = baseline(name=name)["pois"][0]
    model.update(id="wikidata-Q123", wikidata="Q123", category="culture", poi_type="building", lat=51.10001, lon=71.40001, source_p625={"precision": .0001}, source={"name": "Wikidata", "url": "https://www.wikidata.org/wiki/Q123", "license": "CC0", "collected_at": "now", "p31": ["Q41176"]})
    model.update(fields)
    return model


def sidecar(row):
    return {"observed_at": "now", "new_pois": [row]}


def test_a_building_does_not_merge_into_the_business_inside_it():
    result, audit = merge_wikidata(baseline(), sidecar(candidate()), BOUNDARY)
    assert len(result["pois"]) == 2
    assert audit["decisions"] == {"added": 1}
    assert result["pois"][0]["category"] == "cafe"


def test_coarse_coordinates_are_not_published_as_new_precise_urban_destinations():
    result, audit = merge_wikidata(baseline(), sidecar(candidate(source_p625={"precision": .014})), BOUNDARY)
    assert len(result["pois"]) == 1
    assert audit["records"][0]["reason"] == "coarse-or-unknown-coordinate-precision"


def test_exact_source_identity_reuses_the_existing_coordinate_without_duplication():
    data = baseline(name="Historic Site", wikidata="Q123")
    original = deepcopy(data["pois"][0])
    result, audit = merge_wikidata(data, sidecar(candidate(name="Translated Historic Site", lat=51.1003)), BOUNDARY)
    assert len(result["pois"]) == 1
    assert audit["decisions"] == {"matched": 1}
    assert result["pois"][0]["lat"] == original["lat"] and result["pois"][0]["name"] == original["name"]


def test_nearby_church_of_the_same_type_requires_identity_proof():
    data = baseline("place_of_worship", "Full long historical church name")
    result, audit = merge_wikidata(data, sidecar(candidate(name="Different translated church label", poi_type="cathedral")), BOUNDARY)
    assert len(result["pois"]) == 1
    assert audit["records"][0]["reason"] == "nearby-same-physical-type-without-identity-proof"


def linked_entity(qid, name, classes):
    return {"id": qid, "labels": {"en": {"value": name}}, "aliases": {}, "claims": {
        "P625": [{"mainsnak": {"datavalue": {"value": {"latitude": 51.1, "longitude": 71.4, "precision": .00001, "globe": "http://www.wikidata.org/entity/Q2"}}}}],
        "P31": [{"mainsnak": {"datavalue": {"value": {"id": cls}}}} for cls in classes]}}


@pytest.mark.parametrize("explicit_qid", [False, True])
def test_circus_cannot_resolve_to_the_nearby_same_named_fountain(explicit_qid):
    poi = baseline("fountain", "Circus")["pois"][0]
    if explicit_qid:
        poi["wikidata"] = "Q21843144"
    resolved, audit = resolve_entities([poi], {"Q21843144": linked_entity("Q21843144", "Circus", ["Q16889960"])})
    assert resolved == {}
    assert audit[0]["reason"] == "contradictory-physical-types"
    assert not audit[0]["accepted"]


def test_actual_circus_mapped_as_arts_centre_remains_eligible():
    poi = baseline("arts_centre", "City Circus")["pois"][0]
    assert resolve_entities([poi], {"Q21843144": linked_entity("Q21843144", "City Circus", ["Q16889960"])})[0] == {poi["id"]: "Q21843144"}


@pytest.mark.parametrize("explicit_qid", [False, True])
def test_circus_merge_rejects_fountain_even_with_existing_qid(explicit_qid):
    data = baseline("fountain", "Circus", **({"wikidata": "Q123"} if explicit_qid else {}))
    original = deepcopy(data["pois"][0])
    row = candidate("Circus", poi_type="circus", source={"name": "Wikidata", "url": "https://www.wikidata.org/wiki/Q123", "license": "CC0", "p31": ["Q16889960"]})
    result, audit = merge_wikidata(data, sidecar(row), BOUNDARY)
    assert audit["records"][0]["reason"] == "contradictory-physical-types"
    assert result["pois"] == [original]


@pytest.mark.parametrize("kind", ["cafe", "restaurant", "bar"])
def test_monument_does_not_identify_an_unrelated_same_named_business(kind):
    data = baseline(kind, "Memorial")
    row = candidate("Memorial", poi_type="monument", source={"name": "Wikidata", "url": "https://www.wikidata.org/wiki/Q123", "license": "CC0", "p31": ["Q4989906"]})
    result, audit = merge_wikidata(data, sidecar(row), BOUNDARY)
    assert len(result["pois"]) == 1
    assert result["pois"][0]["wikidata"] is None
    assert audit["records"][0]["reason"] == "contradictory-physical-types"
    poi = data["pois"][0]
    assert resolve_entities([poi], {"Q123": linked_entity("Q123", "Memorial", ["Q4989906"])})[0] == {}


def test_organization_with_a_building_class_cannot_be_used_as_branch_identity():
    poi = baseline("cafe", "Brand", wikidata="Q123")["pois"][0]
    classes = ["Q41176", "Q4830453"]
    assert resolve_entities([poi], {"Q123": linked_entity("Q123", "Brand", classes)})[0] == {}
    row = candidate("Brand", source={"name": "Wikidata", "url": "https://www.wikidata.org/wiki/Q123", "license": "CC0", "p31": classes})
    result, audit = merge_wikidata({"metadata": {}, "pois": [poi]}, sidecar(row), BOUNDARY)
    assert len(result["pois"]) == 1
    assert audit["records"][0]["reason"] == "nonphysical-organization-or-brand-identity"


def test_architectural_mall_identity_is_not_rejected_by_building_type():
    data = transform({"elements": [{"type": "way", "id": 1, "center": {"lat": 51.1, "lon": 71.4}, "tags": {"name": "Abu Dhabi Plaza", "shop": "mall", "building": "yes", "wikidata": "Q123"}}]}, "fixture", "now")
    row = candidate("Abu Dhabi Plaza")
    result, audit = merge_wikidata(data, sidecar(row), BOUNDARY)
    assert len(result["pois"]) == 1 and audit["decisions"] == {"matched": 1}
    assert resolve_entities(data["pois"], {"Q123": linked_entity("Q123", "Abu Dhabi Plaza", ["Q41176"])})[0] == {"osm-way-1": "Q123"}


def osm_physical(kind="way", **tags):
    return transform({"elements": [{"type": kind, "id": 240592107, "center": {"lat": 51.1, "lon": 71.4},
        "tags": {"name": "Успенский кафедральный собор", "amenity": "place_of_worship", **tags}}]}, "fixture", "now")["pois"][0]


def reverse_entity(kind="way", value="240592107", **fields):
    entity = linked_entity("Q1899549", "Cathedral with a different translated name", ["Q2977"])
    entity["claims"]["P10689" if kind == "way" else "P402"] = [{"mainsnak": {"datavalue": {"value": value}}, **fields}]
    return entity


@pytest.mark.parametrize("kind", ["way", "relation"])
def test_exact_reverse_osm_identity_can_resolve_different_translated_label(kind):
    poi = osm_physical(kind)
    original = deepcopy(poi)
    resolved, audit = resolve_entities([poi], {"Q1899549": reverse_entity(kind)})
    assert resolved == {poi["id"]: "Q1899549"}
    assert audit[0]["accepted"] and audit[0]["method"] == "exact reverse OSM identity claim and coordinates"
    assert poi == original


@pytest.mark.parametrize("value", [240592107, True, "240592107x", " 240592107", "0240592107", "٢٤٠٥٩٢١٠٧", "-240592107"])
def test_reverse_osm_requires_unambiguous_canonical_decimal_string(value):
    assert resolve_entities([osm_physical()], {"Q1899549": reverse_entity(value=value)})[0] == {}


def test_deprecated_reverse_claim_is_not_an_identity_link():
    assert resolve_entities([osm_physical()], {"Q1899549": reverse_entity(rank="deprecated")})[0] == {}


@pytest.mark.parametrize("problem", ["missing", "distant", "boolean", "nonfinite"])
def test_reverse_osm_link_still_requires_actual_nearby_earth_coordinates(problem):
    entity = reverse_entity()
    if problem == "missing": entity["claims"].pop("P625")
    else:
        coordinate = entity["claims"]["P625"][0]["mainsnak"]["datavalue"]["value"]
        coordinate["latitude"] = {"distant": 51.2, "boolean": True, "nonfinite": float("nan")}[problem]
    resolved, audit = resolve_entities([osm_physical()], {"Q1899549": entity})
    assert resolved == {}
    assert audit[0]["reason"] == "missing or contradictory physical coordinates"


def test_reverse_osm_link_cannot_override_conflicting_existing_wikidata():
    resolved, audit = resolve_entities([osm_physical(wikidata="Q999")], {"Q1899549": reverse_entity()})
    assert resolved == {}
    assert audit[0]["reason"] == "conflicting existing Wikidata identity"


def test_reverse_osm_link_cannot_override_contradictory_physical_type():
    poi = osm_physical(amenity="fountain")
    resolved, audit = resolve_entities([poi], {"Q1899549": reverse_entity()})
    assert resolved == {}
    assert audit[0]["reason"] == "contradictory-physical-types"


@pytest.mark.parametrize("same_entity", [False, True])
def test_duplicate_reverse_claims_are_rejected_even_when_a_name_also_matches(same_entity):
    first = reverse_entity()
    first["labels"]["ru"] = {"value": "Успенский кафедральный собор"}
    if same_entity:
        first["claims"]["P10689"] *= 2
        entities = {"Q1899549": first}
    else:
        second = reverse_entity()
        second["id"] = "Q999"
        entities = {"Q1899549": first, "Q999": second}
    resolved, audit = resolve_entities([osm_physical()], entities)
    assert resolved == {}
    assert all(not item["accepted"] for item in audit)
    assert all(item["reason"] == "ambiguous or duplicate reverse OSM identity claims" for item in audit)


def test_reverse_osm_id_alone_cannot_bind_a_foreign_primary_source():
    poi = osm_physical()
    poi["source"]["url"] = "https://third-party.example/way/240592107"
    assert resolve_entities([poi], {"Q1899549": reverse_entity()})[0] == {}
