import copy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from scripts.apply_operator_corrections import (apply_operator_corrections, apply_retained_operator_corrections,
                                                CORRECTION_ID, GERS_ID, OPERATOR_URL, SIDECAR_NAME, TARGET_ID, TARGET_NAME, TARGET_POINT)
from scripts.refresh_dataset import merge_retained_collections, refresh_live


def fixture():
    excerpt = "As of December 2024, the Future Energy Museum has completed its work and stopped receiving visitors."
    source = {"url": OPERATOR_URL, "observed_at": "2026-10-20T17:00:00+00:00", "body_sha256": "a" * 64,
              "excerpts": [excerpt], "excerpts_sha256": hashlib.sha256(excerpt.encode()).hexdigest()}
    poi = {"id": TARGET_ID, "name": TARGET_NAME, "lat": TARGET_POINT[0], "lon": TARGET_POINT[1], "recommendable": True,
           "description": "Original description", "phone": "+77170000000", "category": "museum", "operating_status": None,
           "source": {"name": "Overture Maps", "gers_id": GERS_ID, "url": "https://explore.overturemaps.org/?id=" + GERS_ID,
                      "original_sources": [{"dataset": "meta"}], "collected_at": "2026-10-20T12:00:00Z"}}
    dataset = {"metadata": {"count": 2}, "pois": [poi, {"id": "different-place", "name": "Current museum", "recommendable": True}]}
    sidecar = {"schema_version": 1, "corrections": [{"id": CORRECTION_ID,
               "target": {"id": TARGET_ID, "name": TARGET_NAME, "lat": TARGET_POINT[0], "lon": TARGET_POINT[1], "source_name": "Overture Maps", "gers_id": GERS_ID},
               "facts": {"operating_status": "closed", "recommendable": False, "closed_since": "2024-12"}, "sources": [source]}]}
    return dataset, sidecar


def test_correction_only_disables_obsolete_entity_preserving_original_facts_and_provenance():
    dataset, sidecar = fixture(); original = copy.deepcopy(dataset)
    result = apply_operator_corrections(dataset, sidecar)
    poi = result["pois"][0]
    assert poi["recommendable"] is False and poi["operating_status"] == "closed"
    for key in ("id", "name", "description", "phone", "category", "source", "lat", "lon"):
        assert poi[key] == original["pois"][0][key]
    assert result["pois"][1] == original["pois"][1] and len(result["pois"]) == 2
    assert poi["operating_status_source"]["url"] == OPERATOR_URL
    assert poi["operating_status_source"]["observed_at"] == sidecar["corrections"][0]["sources"][0]["observed_at"]
    assert result["metadata"]["operator_corrections"]["applied"][0]["id"] == CORRECTION_ID


def test_correction_is_idempotent_and_does_not_modify_retained_evidence():
    dataset, sidecar = fixture(); original = copy.deepcopy(sidecar)
    first = copy.deepcopy(apply_operator_corrections(dataset, sidecar))
    assert apply_operator_corrections(dataset, sidecar) == first and sidecar == original
    assert len(dataset["pois"][0]["source_corrections"]) == 1


@pytest.mark.parametrize("problem", ["id", "name", "gers", "source_url", "coordinate", "target_coordinate", "missing_target",
                                     "digest", "body_digest", "excerpt_claim", "too_long", "timestamp", "action", "numeric_false", "operator"])
def test_bad_identity_action_or_evidence_fails_before_any_dataset_mutation(problem):
    dataset, sidecar = fixture(); correction = sidecar["corrections"][0]; source = correction["sources"][0]
    if problem == "id": correction["target"]["id"] = "different-place"
    elif problem == "name": dataset["pois"][0]["name"] = "Singularity Museum"
    elif problem == "gers": dataset["pois"][0]["source"]["gers_id"] = "other"
    elif problem == "source_url": dataset["pois"][0]["source"]["url"] += "0"
    elif problem == "coordinate": dataset["pois"][0]["lat"] += 0.02
    elif problem == "target_coordinate": correction["target"]["lon"] += 0.02
    elif problem == "missing_target": dataset["pois"] = dataset["pois"][1:]
    elif problem == "digest": source["excerpts_sha256"] = "b" * 64
    elif problem == "body_digest": source["body_sha256"] = "missing"
    elif problem == "excerpt_claim": source["excerpts"] = ["Nur Alem Museum is open since December 2024."]; source["excerpts_sha256"] = hashlib.sha256(source["excerpts"][0].encode()).hexdigest()
    elif problem == "too_long": source["excerpts"] = [source["excerpts"][0] + " more" * 30]; source["excerpts_sha256"] = hashlib.sha256(source["excerpts"][0].encode()).hexdigest()
    elif problem == "timestamp": source["observed_at"] = "2026-10-20T17:00:00"
    elif problem == "action": correction["facts"]["recommendable"] = True
    elif problem == "numeric_false": correction["facts"]["recommendable"] = 0
    elif problem == "operator": source["url"] = "https://third-party.example/closure"
    before = copy.deepcopy(dataset)
    with pytest.raises(ValueError): apply_operator_corrections(dataset, sidecar)
    assert dataset == before


def test_optional_sidecar_absent_leaves_fixture_unchanged_and_merge_reapplies_present_evidence(tmp_path):
    dataset, sidecar = fixture(); original = copy.deepcopy(dataset)
    assert apply_retained_operator_corrections(dataset, tmp_path) == original
    raw = tmp_path / "data/raw"; raw.mkdir(parents=True)
    (raw / SIDECAR_NAME).write_text(json.dumps(sidecar))
    result = merge_retained_collections(dataset, tmp_path)
    assert result["pois"][0]["recommendable"] is False
    assert result["pois"][0]["operating_status"] == "closed"


def test_invalid_retained_sidecar_does_not_silently_reenable_or_change_any_place(tmp_path):
    dataset, sidecar = fixture(); original = copy.deepcopy(dataset)
    sidecar["corrections"][0]["sources"] = []
    raw = tmp_path / "data/raw"; raw.mkdir(parents=True)
    (raw / SIDECAR_NAME).write_text(json.dumps(sidecar))
    with pytest.raises(ValueError): merge_retained_collections(dataset, tmp_path)
    assert dataset == original


def test_live_refresh_reapplies_retained_closure_after_later_enrichment(tmp_path, monkeypatch):
    dataset, sidecar = fixture()
    raw = tmp_path / "data/raw"; raw.mkdir(parents=True)
    (raw / SIDECAR_NAME).write_text(json.dumps(sidecar))
    captured = {}

    def run(command, **kwargs):
        name = command[1].rsplit("/", 1)[-1]
        flag = "--output" if name == "collect_pois.py" else "--input" if name == "enrich_poi_media.py" else "--dataset"
        path = Path(command[command.index(flag) + 1])
        if name == "collect_pois.py":
            path.write_text(json.dumps(dataset))
        elif name == "enrich_poi_reviews.py":
            value = json.loads(path.read_text())
            value["pois"][0]["recommendable"] = True
            value["pois"][0]["operating_status"] = None
            path.write_text(json.dumps(value))

    def export(path, **kwargs):
        captured.update(json.loads(path.read_text()))
        return {"validated": True}

    monkeypatch.setitem(sys.modules, "export_poi_dataset", SimpleNamespace(export_dataset=export))
    assert refresh_live(tmp_path, run=run) == {"validated": True}
    assert captured["pois"][0]["recommendable"] is False and captured["pois"][0]["operating_status"] == "closed"
    assert not (tmp_path / "data/pois.json").exists()
