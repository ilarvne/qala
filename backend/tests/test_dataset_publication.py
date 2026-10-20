"""Publication failures must not damage the last usable normalized dataset."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from scripts.collect_pois import transform
from scripts import export_poi_dataset as exporter
from scripts.refresh_dataset import refresh_live, replay_dataset

ROOT = Path(__file__).resolve().parents[2]
NORMALIZED = ("pois.json", "pois.csv", "pois.geojson", "dataset-manifest.json", "photo-attributions.json", "review-attributions.json")


def fixture(tmp_path):
    project = tmp_path / "project"
    (project / "data").mkdir(parents=True)
    for name in NORMALIZED:
        (project / "data" / name).write_bytes(("previous-" + name).encode())
    raw = {"elements": [{"type": "node", "id": 1, "lat": 51.1, "lon": 71.4, "tags": {"name": "Source cafe", "amenity": "cafe"}}]}
    dataset = transform(raw, "test", "2026-10-19T00:00:00Z")
    source = tmp_path / "candidate.json"
    source.write_text(json.dumps(dataset))
    sidecars = {}
    for name, field in (("photo-attributions.json", "photos"), ("review-attributions.json", "reviews")):
        sidecars[name] = tmp_path / name
        sidecars[name].write_text(json.dumps({field: [], "metadata": {}}))
    return project, source, dataset, sidecars


def snapshot(project):
    return {name: (project / "data" / name).read_bytes() for name in NORMALIZED}


@pytest.mark.parametrize("problem", ["duplicate", "coordinate", "rating", "missing_photo", "count"])
def test_invalid_candidate_never_changes_published_normalized_files(tmp_path, problem):
    project, source, dataset, sidecars = fixture(tmp_path)
    before = snapshot(project)
    poi = dataset["pois"][0]
    if problem == "duplicate":
        dataset["pois"].append(dict(poi)); dataset["metadata"]["count"] = 2; dataset["metadata"]["coverage"]["total"] = 2
    elif problem == "coordinate":
        poi["lat"] = float("nan")
    elif problem == "rating":
        poi["rating"] = 4.8
    elif problem == "missing_photo":
        poi["photos"] = [{"url": "/photos/missing.jpg", "source_url": "https://commons.wikimedia.org/a", "license": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/", "attribution": "Author"}]
    else:
        dataset["metadata"]["count"] = 99
    source.write_text(json.dumps(dataset))
    with pytest.raises(ValueError):
        exporter.export_dataset(source, project_root=project, sidecars=sidecars)
    assert snapshot(project) == before


def test_export_render_failure_preserves_all_six_published_files(tmp_path, monkeypatch):
    project, source, _, sidecars = fixture(tmp_path)
    before = snapshot(project)
    def fail_render(*args):
        (args[1] / "pois.csv").write_text("partial staged csv")
        raise OSError("Controlled export write failure")
    monkeypatch.setattr(exporter, "_render_exports", fail_render)
    with pytest.raises(OSError):
        exporter.export_dataset(source, project_root=project, sidecars=sidecars)
    assert snapshot(project) == before


def test_last_publication_replace_failure_rolls_back_json_exports_and_attributions(tmp_path, monkeypatch):
    project, source, _, sidecars = fixture(tmp_path)
    before = snapshot(project)
    actual_replace = exporter.os.replace
    failed = False
    def fail_last(source_path, destination):
        nonlocal failed
        if Path(destination).name == "review-attributions.json" and not failed:
            failed = True
            raise OSError("Controlled sixth-file replacement failure")
        return actual_replace(source_path, destination)
    monkeypatch.setattr(exporter.os, "replace", fail_last)
    with pytest.raises(OSError):
        exporter.export_dataset(source, project_root=project, sidecars=sidecars)
    assert failed and snapshot(project) == before


def test_later_enrichment_failure_restores_shared_attribution_files(tmp_path):
    project, source, _, _ = fixture(tmp_path)
    before = snapshot(project)
    def controlled_run(command, **_):
        name = Path(command[1]).name
        if name == "collect_pois.py":
            Path(command[command.index("--output") + 1]).write_bytes(source.read_bytes())
        elif name == "enrich_poi_media.py":
            (project / "data/photo-attributions.json").write_text('{"photos": [], "metadata": {"new": true}}')
        else:
            (project / "data/review-attributions.json").write_text("partial new manifest")
            raise subprocess.CalledProcessError(1, command)
    with pytest.raises(subprocess.CalledProcessError):
        refresh_live(project, run=controlled_run)
    assert snapshot(project) == before


def test_valid_candidate_publishes_consistent_hashes_and_all_six_files(tmp_path):
    project, source, _, sidecars = fixture(tmp_path)
    report = exporter.export_dataset(source, project_root=project, sidecars=sidecars)
    assert all(report["validation"].values())
    assert (project / "data/pois.json").read_bytes() == source.read_bytes()
    for entry in report["files"]:
        assert hashlib.sha256((project / entry["path"]).read_bytes()).hexdigest() == entry["sha256"]
    assert json.loads((project / "data/photo-attributions.json").read_text())["photos"] == []


def test_archive_style_replay_without_full_operator_html_preserves_real_coverage(tmp_path):
    project = tmp_path / "archive"
    (project / "data/raw").mkdir(parents=True)
    for name in ("pois.json", "photo-attributions.json", "photo-curation.json"):
        (project / "data" / name).symlink_to(ROOT / "data" / name)
    for evidence in (ROOT / "data/raw").iterdir():
        if evidence.suffix != ".html":
            (project / "data/raw" / evidence.name).symlink_to(evidence, target_is_directory=evidence.is_dir())
    (project / "public").symlink_to(ROOT / "public", target_is_directory=True)
    assert not list((project / "data/raw").glob("*.html"))
    original = hashlib.sha256((ROOT / "data/pois.json").read_bytes()).hexdigest()
    replayed = replay_dataset(project)
    assert replayed["metadata"]["coverage"] == json.loads((ROOT / "data/pois.json").read_text())["metadata"]["coverage"]
    assert replayed["metadata"]["operator_enrichment"]["count"] == 2
    assert hashlib.sha256((ROOT / "data/pois.json").read_bytes()).hexdigest() == original
    assert all(item["word_count"] <= 25 for item in json.loads((project / "data/raw/operator-source-excerpts.json").read_text())["sources"])


def test_curation_publication_failure_rolls_back_all_seven_files(tmp_path, monkeypatch):
    project, source, _, sidecars = fixture(tmp_path)
    (project / "data/photo-curation.json").write_text("previous-curation")
    before = {**snapshot(project), "photo-curation.json": b"previous-curation"}
    curation = tmp_path / "curation.json"
    curation.write_text('{"excluded_files": {}}')
    sidecars["photo-curation.json"] = curation
    actual_replace = exporter.os.replace
    failed = False
    def fail_curation(source_path, destination):
        nonlocal failed
        if Path(destination).name == "photo-curation.json" and not failed:
            failed = True
            raise OSError("Controlled seventh-file publication failure")
        return actual_replace(source_path, destination)
    monkeypatch.setattr(exporter.os, "replace", fail_curation)
    with pytest.raises(OSError):
        exporter.export_dataset(source, project_root=project, sidecars=sidecars)
    assert failed
    assert {name: (project / "data" / name).read_bytes() for name in before} == before
