import copy
import csv
import hashlib
import json
import socket
import sys

import pytest

from scripts.providers.common import correlate
from scripts.providers.review_queue import build_review_queue, comparison_csv_rows, review_csv_rows, safe_csv_cell


TIME = "2026-10-20T16:00:00Z"
POI = {"id": "osm-node-1", "name": "Example Cafe", "names": {}, "lat": 51.1, "lon": 71.4,
       "category": "cafe", "hours": "Mo-Fr 09:00-18:00", "recommendable": True,
       "source": {"name": "OpenStreetMap", "url": "https://www.openstreetmap.org/node/1", "updated_at": "2023-01-01T00:00:00Z"}}


def observation(**changes):
    return {"provider": "yandex", "provider_id": "123", "source_url": "https://yandex.com/maps/org/example/123/",
            "name": "Example Cafe", "lat": 51.1, "lon": 71.4, "address": "Astana, example1", "rating": 4.8,
            "rating_scale": 5, "rating_count": None, "review_count": 5, "photo_source_links": ["https://photo.example/1"],
            "review_source_links": ["https://yandex.com/maps/org/example/123/reviews/"], "observed_at": TIME,
            "access_method": "http", "http_status": 200, "evidence_sha256": "a" * 64, "matched_poi_ids": [],
            "identity_evidence": [], "import_policy": "evaluation_only", "warnings": [], **changes}


def conflict(**changes):
    return {"id": "operating-status-example", "kind": "operating_status_conflict", "matched_poi_ids": [POI["id"]],
            "provider_observation": {"provider": "yandex", "name": "Example Cafe", "source_url": observation()["source_url"],
                                     "reported_status": "permanently_closed", "observed_at": TIME, "evidence_sha256": "b" * 64,
                                     "evidence_path": "artifacts/provider-crawl/example-visible.json"},
            "independent_operator_confirmation": False, **changes}


def test_nearby_containment_candidates_are_never_identity_assignments_or_corpus_edits():
    pois = [copy.deepcopy(POI), {**copy.deepcopy(POI), "id": "osm-node-2", "lon": 71.4005}]
    before = copy.deepcopy(pois)
    row = correlate(observation(name="Example Cafe West"), pois)
    queue = build_review_queue([row], pois)
    item = queue["items"][0]
    assert item["resolution_state"] == "manual_review" and item["matched_poi_ids"] == []
    assert len(item["candidate_pois"]) == 2 and not any(x["assigned"] for x in item["candidate_pois"])
    assert item["candidate_pois"][0]["local_poi"]["hours"] == POI["hours"]
    assert item["candidate_pois"][0]["local_poi"]["last_edit"] == POI["source"]["updated_at"]
    assert pois == before and row["matched_poi_ids"] == []


def test_substrings_distant_places_and_search_index_coordinates_are_not_candidates():
    for changes in ({"name": "Cafe"}, {"lat": 51.2}, {"access_method": "exa"}):
        poi = {**POI, "name": "Cafela"} if changes.get("name") == "Cafe" else POI
        queue = build_review_queue([correlate(observation(**changes), [poi])], [poi])
        assert queue["items"][0]["candidate_pois"] == []


def test_status_conflict_keeps_current_local_state_and_original_source_evidence():
    row = correlate(observation(), [POI])
    queue = build_review_queue([row], [POI], [conflict()])
    item = queue["items"][0]
    assert item["kind"] == "operating_status_conflict" and item["priority"] == "high"
    assert item["resolution_state"] == "manual_review" and item["identity_verified_by_current_audit"] is True
    assert item["local_pois"][0]["recommendable"] is True
    assert item["provider_observation"]["evidence_sha256"] == "b" * 64
    assert item["provider_observation"]["observed_at"] == TIME
    assert item["provider_observation"]["rating_count"] is None
    assert item["provider_observation"]["photo_source_links"] == row["photo_source_links"]
    assert item["independent_operator_confirmation"] is False
    assert queue["matched_poi_comparisons"][0]["status_review_ids"] == [item["id"]]


def test_status_file_cannot_assign_an_unverified_local_identity_or_reuse_newer_metrics():
    row = correlate(observation(name="Different venue", observed_at="2026-10-20T17:00:00Z"), [POI])
    queue = build_review_queue([row], [POI], [conflict()])
    item = next(item for item in queue["items"] if item["kind"] == "operating_status_conflict")
    assert item["matched_poi_ids"] == [] and item["local_pois"] == []
    assert item["identity_verified_by_current_audit"] is False
    assert item["provider_observation"]["rating"] is None
    assert item["provider_observation"]["rating_count"] is None and item["provider_observation"]["review_count"] is None


def test_provider_differences_keep_separate_populations_and_unknown_counts():
    yandex = correlate(observation(), [POI])
    gis = correlate(observation(provider="2gis", provider_id="456", source_url="https://2gis.kz/astana/firm/456",
                                rating=4.2, rating_count=30, review_count=20), [POI])
    queue = build_review_queue([yandex, gis], [POI])
    comparison = queue["matched_poi_comparisons"][0]
    assert comparison["rating_aggregation_performed"] is False
    assert [item["field"] for item in comparison["disagreements"]] == ["rating", "review_count"]
    assert comparison["provider_observations"][0]["rating_count"] is None
    assert queue["items"] == []
    exported = list(comparison_csv_rows(queue))
    assert len(exported) == 2 and exported[0]["rating_count"] is None
    assert exported[0]["observed_at"] == TIME and exported[0]["local_last_edit"] == POI["source"]["updated_at"]


@pytest.mark.parametrize("value", ["=SUM(1,2)", "+cmd", "-cmd", "@SUM(A1)", "  =FORMULA()", "\tname", "\nname"])
def test_csv_source_text_is_never_a_spreadsheet_formula(value):
    assert safe_csv_cell(value).startswith("'")
    assert safe_csv_cell(4.8) == 4.8


def test_review_csv_preserves_source_refs_time_and_safe_names():
    row = correlate(observation(name="=FORMULA()"), [POI])
    exported = list(review_csv_rows(build_review_queue([row], [POI])))[0]
    assert exported["name"] == "'=FORMULA()" and exported["observed_at"] == TIME
    assert json.loads(exported["photo_source_links"]) == row["photo_source_links"]
    assert json.loads(exported["review_source_links"]) == row["review_source_links"]
    assert exported["rating_count"] is None


def test_quality_evidence_must_be_public_timestamped_and_not_a_private_path():
    bad = conflict(); bad["provider_observation"]["source_url"] += "?X-Amz-Signature=secret"
    with pytest.raises(ValueError, match="public source"):
        build_review_queue([], [POI], [bad])
    bad = conflict(); bad["provider_observation"]["observed_at"] = "2026-10-20T16:00:00"
    with pytest.raises(ValueError, match="public source"):
        build_review_queue([], [POI], [bad])
    bad = conflict(); bad["provider_observation"]["evidence_path"] = "artifacts/../../.env"
    queue = build_review_queue([], [POI], [bad])
    assert queue["items"][0]["provider_observation"]["evidence_path"] is None


@pytest.mark.parametrize("relative_inputs", [False, True])
def test_offline_cli_emits_queue_hashes_and_safe_csv_without_network_or_corpus_changes(tmp_path, monkeypatch, relative_inputs):
    from scripts.audit_map_provider_crawl import main

    dataset = tmp_path / "pois.json"; dataset.write_text(json.dumps({"pois": [POI]})); before = dataset.read_bytes()
    (tmp_path / "first").mkdir(); (tmp_path / "second").mkdir()
    first = tmp_path / "first/rows.json"; first.write_text(json.dumps([observation()]))
    second = tmp_path / "second/rows.json"; second.write_text(json.dumps([observation(name="=FORMULA()", provider_id="789", source_url="https://yandex.com/maps/org/other/789/")]))
    quality = tmp_path / "quality.json"; quality.write_text(json.dumps([conflict()]))
    output = tmp_path / "out"
    monkeypatch.chdir(tmp_path)
    input_paths = [str(path.relative_to(tmp_path) if relative_inputs else path) for path in (first, second)]
    monkeypatch.setattr(sys, "argv", ["audit", "--dataset", str(dataset), "--input", input_paths[0], "--input", input_paths[1], "--quality-conflicts", str(quality), "--output", str(output)])

    def denied(*args, **kwargs):
        raise AssertionError("Offline review attempted network")

    monkeypatch.setattr(socket.socket, "connect", denied); monkeypatch.setattr(socket, "create_connection", denied)
    main()
    queue = json.loads((output / "review-queue.json").read_text())
    assert queue["quality_input_sha256"][quality.name] == hashlib.sha256(quality.read_bytes()).hexdigest()
    assert len(queue["input_sha256"]) == 2 and queue["network_requests"] == 0
    assert set(queue["input_sha256"].values()) == {hashlib.sha256(path.read_bytes()).hexdigest() for path in (first, second)}
    assert queue["counts"]["manual_review_items"] == 2
    assert dataset.read_bytes() == before
    with (output / "observations.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert any(row["name"] == "'=FORMULA()" for row in rows)
    assert all(row["rating_count"] == "" for row in rows)
    assert (output / "provider-comparisons.csv").exists()


def test_audit_cannot_overwrite_its_input_corpus(tmp_path, monkeypatch):
    from scripts.audit_map_provider_crawl import main

    dataset = tmp_path / "observations.json"; dataset.write_text(json.dumps({"pois": [POI]})); before = dataset.read_bytes()
    monkeypatch.setattr(sys, "argv", ["audit", "--dataset", str(dataset), "--output", str(tmp_path), "--no-quality-conflicts"])
    with pytest.raises(ValueError, match="overwrite"):
        main()
    assert dataset.read_bytes() == before
