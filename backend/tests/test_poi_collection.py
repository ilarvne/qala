"""Data boundaries and evidence parsing; no live services in unit tests."""
from scripts.collect_pois import transform
from scripts.enrich_poi_media import clean_html, commons_photo
from scripts.enrich_poi_reviews import enrich_reviews, verify_review
from pathlib import Path
import copy
import json


def point(identifier, kind, **tags):
    return {"type": "node", "id": identifier, "lat": 51.1, "lon": 71.4, "timestamp": "2026-10-19T00:00:00Z", "version": 3,
            "tags": {"amenity": kind, **tags}}


def test_city_inventory_preserves_exact_food_categories_and_unknown_evidence():
    result = transform({"elements": [point(1, "cafe", name="Coffee"), point(2, "restaurant", name="Dinner"), point(3, "pub", name="Night")]}, "fixture", "now")
    assert [p["category"] for p in result["pois"]] == ["cafe", "dining", "nightlife"]
    assert all(p["rating"] is None and p["reviews"] == [] and p["photos"] == [] for p in result["pois"])
    assert all(p["source"]["version"] == 3 and p["source"]["updated_at"] == "2026-10-19T00:00:00Z" for p in result["pois"])
    assert all(p["amenities"]["power_supply"] is None for p in result["pois"])


def test_dedup_does_not_erase_adjacent_unnamed_public_features():
    raw = {"elements": [point(1, "drinking_water"), point(2, "drinking_water"), point(3, "cafe", name="Same cafe"), point(4, "cafe", name="Same cafe")]}
    pois = transform(raw, "fixture", "now")["pois"]
    assert len(pois) == 3
    assert pois[-1]["duplicate_source_ids"] == ["osm-node-4"]
    assert sum(p["name_derived"] for p in pois) == 2


def test_private_access_is_explicitly_not_recommendable():
    poi = transform({"elements": [point(1, "cafe", name="Members", access="private", wheelchair="limited", **{"wheelchair:description": "one step", "step_count": "1"})]}, "fixture", "now")["pois"][0]
    assert poi["recommendable"] is False
    assert poi["accessibility"]["wheelchair"] == "limited"
    assert poi["accessibility"]["step_count"] == "1"
    assert poi["accessibility"]["wheelchair_description"] == "one step"


def test_explicit_outdoor_cafe_does_not_become_indoor_by_category():
    poi = transform({"elements": [point(1, "cafe", name="Outdoor coffee", indoor="no")]}, "fixture", "now")["pois"][0]
    assert poi["indoor"] is False
    assert poi["indoor_evidence"] == "source-tag"


def photo_page(license_name="CC BY-SA 4.0", author='<a href="https://example.org">Author &amp; photographer</a>'):
    return {"title": "File:Real place.jpg", "imageinfo": [{"mime": "image/jpeg", "url": "https://upload.wikimedia.org/real.jpg", "descriptionurl": "https://commons.wikimedia.org/wiki/File:Real_place.jpg", "extmetadata": {"LicenseShortName": {"value": license_name}, "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0/"}, "Artist": {"value": author}, "AttributionRequired": {"value": "true"}}}]}


def test_photo_evidence_requires_reusable_license_and_sanitized_credit():
    photo = commons_photo(photo_page(), "now")
    assert photo["author"] == "Author & photographer"
    assert "<" not in photo["attribution"]
    assert photo["source_url"].startswith("https://commons.wikimedia.org/wiki/File:")
    assert commons_photo(photo_page("All rights reserved"), "now") is None
    assert commons_photo(photo_page(author=""), "now") is None
    assert clean_html('<script>text</script><b> &amp; Author</b>') == "text & Author"


def test_real_signed_mangrove_rating_and_tamper_rejection():
    # This public signed snapshot is an actual source record, not a made-up
    # testimonial. Its API payload has reordered geo parameters in the subject.
    raw = json.loads((Path(__file__).resolve().parents[2] / "data/raw/mangrove-astana-bbox.json").read_text())
    record = raw["reviews"][0]
    assert verify_review(record)
    tampered = copy.deepcopy(record)
    tampered["payload"]["rating"] = 100
    assert not verify_review(tampered)
    tampered = copy.deepcopy(record)
    tampered["signature"] = "bad"
    assert not verify_review(tampered)


def test_signed_rating_only_review_does_not_invent_an_opinion_or_cross_match():
    raw = json.loads((Path(__file__).resolve().parents[2] / "data/raw/mangrove-astana-bbox.json").read_text())
    dataset = transform({"elements": [point(14201388401, "cafe", name="Overhead")]}, "fixture", "now")
    dataset["pois"][0].update(lat=51.1479049, lon=71.3879847)
    enrich_reviews(dataset, raw, "now")
    poi = dataset["pois"][0]
    assert poi["rating"] == 3.5 and poi["rating_count"] == 1
    assert poi["reviews"][0]["text"] is None
    assert poi["reviews"][0]["signature_verified"] is True
    assert poi["reviews"][0]["license"] == "CC-BY-4.0"
    unrelated = transform({"elements": [point(1, "cafe", name="Unrelated")]}, "fixture", "now")
    enrich_reviews(unrelated, raw, "now")
    assert unrelated["pois"][0]["rating"] is None
