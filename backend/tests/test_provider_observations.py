import copy
import json
import socket
import sys

import pytest

from scripts.providers.common import correlate, validate_observation


def observation(**overrides):
    return {"provider": "yandex", "provider_id": "12345", "source_url": "https://yandex.kz/maps/org/branch/12345/?utm_source=test",
            "name": "Бәйтерек", "lat": 51.12828, "lon": 71.43045, "address": None, "rating": 4.8, "rating_scale": 5,
            "rating_count": None, "review_count": 30, "photo_source_links": [], "review_source_links": [],
            "observed_at": "2026-10-20T16:00:00+00:00", "access_method": "http", "http_status": 200,
            "evidence_sha256": "a" * 64, "matched_poi_ids": ["untrusted-client-match"], "identity_evidence": [],
            "warnings": [], "import_policy": "evaluation_only", **overrides}


POI = {"id": "osm-way-1", "name": "Bayterek", "names": {"ru": "Байтерек", "kk": "Бәйтерек"}, "lat": 51.128288, "lon": 71.430454}


def test_ratings_and_written_review_counters_are_not_interchangeable():
    row = validate_observation(observation())
    assert row["rating_count"] is None and row["review_count"] == 30
    assert row["matched_poi_ids"] == []
    assert row["source_url"] == "https://yandex.kz/maps/org/branch/12345/"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, -1, 6, "4.9"])
def test_invalid_rating_does_not_become_a_fact(value):
    assert validate_observation(observation(rating=value))["rating"] is None


@pytest.mark.parametrize("url", ["https://yandex.kz.evil.example/maps/org/12345/", "https://user:pass@yandex.kz/maps/org/12345/", "https://yandex.kz/maps/org/99999/", "https://yandex.kz/maps/org/12345/?api_key=private", "javascript:alert(1)"])
def test_entity_source_must_be_exact_public_credential_free_url(url):
    with pytest.raises(ValueError):
        validate_observation(observation(source_url=url))


def test_scraped_private_fields_and_unapproved_import_state_are_not_forwarded():
    row = validate_observation(observation(review_text="not copied", session_nonce="private", raw_html="not copied"))
    assert not {"review_text", "session_nonce", "raw_html"} & row.keys()
    with pytest.raises(ValueError, match="licence"):
        validate_observation(observation(import_policy="publish"))


@pytest.mark.parametrize("parameter", ["X-Amz-Signature", "X-Amz-Credential", "X-Goog-Signature", "x-api-key", "client_secret", "auth", "session_token", "refresh_token"])
def test_signed_or_credentialed_media_references_are_not_exported(parameter):
    private = "https://photo.example/image?" + parameter + "=not-a-real-secret"
    public = "https://photo.example/image?width=500"
    row = validate_observation(observation(photo_source_links=[private, public], review_source_links=[private]))
    assert row["photo_source_links"] == [public]
    assert row["review_source_links"] == []


@pytest.mark.parametrize("overrides", [{}, {"name": "Other venue"}, {"lat": None}, {"access_method": "exa"}])
def test_correlating_an_already_correlated_row_is_idempotent(overrides):
    first = correlate(observation(**overrides), [POI])
    assert correlate(first, [POI]) == first


def test_exact_name_and_nearby_entity_coordinates_are_both_required():
    assert correlate(observation(), [POI])["matched_poi_ids"] == [POI["id"]]
    assert correlate(observation(lat=51.2), [POI])["matched_poi_ids"] == []
    assert correlate(observation(name="Baiterek Coffee"), [POI])["matched_poi_ids"] == []
    assert correlate(observation(lat=None), [POI])["matched_poi_ids"] == []


def test_duplicate_nearby_branch_names_are_quarantined():
    duplicate = {**POI, "id": "osm-way-2"}
    assert correlate(observation(), [POI, duplicate])["matched_poi_ids"] == []


def test_search_snippet_does_not_create_live_source_match():
    assert correlate(observation(access_method="exa"), [POI])["matched_poi_ids"] == []


def test_replay_keeps_acquisition_time_and_does_not_mutate_corpus():
    original = copy.deepcopy(POI)
    row = correlate(observation(), [POI])
    assert row["observed_at"] == "2026-10-20T16:00:00+00:00" and POI == original


def test_2gis_firm_id_and_museum_country_abbreviation():
    place = {"id": "osm-node-1", "name": "Национальный музей Республики Казахстан", "lat": 51.12828, "lon": 71.43045}
    row = observation(provider="2gis", source_url="https://2gis.kz/astana/firm/12345", name="Национальный музей РК")
    assert correlate(row, [place])["matched_poi_ids"] == [place["id"]]
    with pytest.raises(ValueError, match="Entity ID"):
        validate_observation({**row, "provider_id": "99999"})


def test_google_canonical_entity_cannot_be_swapped_for_nearby_business():
    row = observation(provider="google", provider_id="0x123:0x456", source_url="https://www.google.com/maps/place/Example/data=!1s0x123:0x456!8m2!3d51.1!4d71.4")
    assert validate_observation(row)["provider_id"] == "0x123:0x456"
    with pytest.raises(ValueError, match="Google entity"):
        validate_observation({**row, "provider_id": "0x123:0x789"})


def test_combined_offline_audit_preserves_provider_boundaries_and_latest_unknowns(tmp_path, monkeypatch):
    from scripts.audit_map_provider_crawl import main

    dataset = tmp_path / "pois.json"
    dataset.write_text(json.dumps({"pois": [POI]}))
    before = dataset.read_bytes()
    records = tmp_path / "records.json"
    older = observation(rating=4.5, rating_count=100, observed_at="2026-10-20T15:00:00Z")
    newer = observation(rating=4.8, rating_count=None, observed_at="2026-10-20T16:00:00Z")
    other = observation(provider="2gis", provider_id="99999", source_url="https://2gis.kz/astana/firm/99999", rating=4.9, rating_count=800)
    records.write_text(json.dumps([newer, other, older]))
    output = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["audit", "--dataset", str(dataset), "--input", str(records), "--output", str(output)])
    network_attempts = []

    def denied(*args, **kwargs):
        network_attempts.append(True)
        raise AssertionError("Offline audit attempted network")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    main()
    result = json.loads((output / "observations.json").read_text())
    assert result["counts"]["observations"] == 2 and result["counts"]["matched"] == 2
    by_provider = {row["provider"]: row for row in result["observations"]}
    assert by_provider["yandex"]["rating_count"] is None
    assert by_provider["yandex"]["rating"] == 4.8 and by_provider["2gis"]["rating"] == 4.9
    assert dataset.read_bytes() == before and network_attempts == []
    assert all(row["import_policy"] == "evaluation_only" for row in result["observations"])
