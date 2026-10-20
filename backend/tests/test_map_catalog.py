"""Every visible corpus entity must be addressable in the GPU map source."""
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from backend.main import app


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os
    old = os.environ.get("QALA_MEMORY_PATH")
    os.environ["QALA_MEMORY_PATH"] = str(tmp_path_factory.mktemp("catalog-memory") / "test.sqlite3")
    with TestClient(app) as test_client:
        yield test_client
    if old is None:
        os.environ.pop("QALA_MEMORY_PATH", None)
    else:
        os.environ["QALA_MEMORY_PATH"] = old


def test_full_visible_inventory_and_exact_coordinates(client):
    corpus = json.loads((Path(__file__).resolve().parents[2] / "data/pois.json").read_text())["pois"]
    visible = {p["id"]: p for p in corpus if str(p.get("operating_status", "")).strip().casefold() != "closed"}
    response = client.get("/api/pois/map")
    assert response.status_code == 200
    catalog = response.json()
    assert catalog["type"] == "FeatureCollection"
    assert {f["id"] for f in catalog["features"]} == set(visible)
    assert len(catalog["features"]) == len(visible)
    for feature in catalog["features"]:
        source = visible[feature["id"]]
        assert feature["geometry"] == {"type": "Point", "coordinates": [source["lon"], source["lat"]]}
        assert feature["properties"]["id"] == source["id"]
        assert feature["properties"]["name"] == source["name"]
        assert feature["properties"]["category"] == source["category"]
    for identifier in list(visible)[::1000]:
        assert client.get("/api/pois/" + identifier).json()["poi"]["id"] == identifier


def test_map_source_is_compact_and_never_contains_provider_profiles(client):
    response = client.get("/api/pois/map")
    assert len(response.content) < 2_500_000
    assert response.headers["cache-control"] == "public, max-age=60"
    allowed = {"id", "name", "category", "name_en", "name_ru", "name_kk"}
    for feature in response.json()["features"]:
        assert set(feature["properties"]) <= allowed
        assert not {"raw_tags", "photos", "rating", "reviews", "contacts"}.intersection(feature["properties"])


def test_historical_closed_poi_is_retained_but_not_mapped(client):
    all_pois = client.get("/api/pois?include_closed=true").json()["pois"]
    closed = [p for p in all_pois if p.get("operating_status") == "closed"]
    assert closed
    ids = {f["id"] for f in client.get("/api/pois/map").json()["features"]}
    for poi in closed:
        assert poi["id"] not in ids
        assert client.get("/api/pois/" + poi["id"]).json()["poi"]["id"] == poi["id"]


def test_detail_retains_licensed_media_and_multilingual_identity(client):
    all_pois = client.get("/api/pois").json()["pois"]
    photographed = next(p for p in all_pois if p.get("photos"))
    detail = client.get("/api/pois/" + photographed["id"]).json()["poi"]
    assert detail["photos"] == photographed["photos"]
    assert detail["source"] == photographed["source"]
    assert "raw_tags" not in detail
    assert all(photo.get("license") and photo.get("source_url") for photo in detail["photos"])
