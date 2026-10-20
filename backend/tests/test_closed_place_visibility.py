"""Closed historical entities stay auditable without entering search suggestions."""
import copy
import socket
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from backend.main import app


@pytest.fixture
def client(monkeypatch):
    places = [
        {"id": "closed-museum", "name": "Former Future Energy Museum", "category": "museum", "operating_status": "closed",
         "recommendable": False, "source": {"name": "Overture Maps", "url": "https://example.org/original-entity"},
         "operating_status_source": {"name": "Venue operator", "url": "https://qazexpocongress.kz/en/nur-alem/", "closed_since": "2024-12"},
         "raw_tags": {"private_for_api": "not returned"}},
        {"id": "active-museum", "name": "Current Museum", "category": "museum", "operating_status": "open", "recommendable": True},
        {"id": "unknown-cafe", "name": "Unknown status cafe", "category": "cafe", "operating_status": None, "recommendable": True},
        {"id": "public-toilet", "name": "Public toilet", "category": "utility", "recommendable": False},
    ]
    data = {"metadata": {"count": len(places), "attribution": "Retained fixture sources"}, "pois": places}
    monkeypatch.setattr(app.state, "dataset", data, raising=False)
    monkeypatch.setattr(app.state, "agent", SimpleNamespace(retriever=SimpleNamespace(by_id={p["id"]: p for p in places})), raising=False)

    def denied(*args, **kwargs):
        raise AssertionError("POI visibility requested external network access")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    # No context-manager startup: use only the temporary in-memory dataset and
    # lookup; never initialize live providers or the on-disk agent corpus.
    yield TestClient(app), data


def test_default_search_hides_closed_but_preserves_active_unknown_and_nonrecommendable_utilities(client):
    http, data = client
    before = copy.deepcopy(data)
    response = http.get("/api/pois")
    assert response.status_code == 200
    payload = response.json()
    assert {p["id"] for p in payload["pois"]} == {"active-museum", "unknown-cafe", "public-toilet"}
    assert payload["total"] == 3 and payload["metadata"]["count"] == 4
    assert data == before


def test_closed_name_query_returns_no_suggestion_unless_history_is_explicitly_requested(client):
    http, _ = client
    assert http.get("/api/pois", params={"q": "Former Future Energy"}).json()["pois"] == []
    result = http.get("/api/pois", params={"q": "Former Future Energy", "include_closed": "true"}).json()
    assert result["total"] == 1 and result["pois"][0]["id"] == "closed-museum"
    assert result["pois"][0]["operating_status_source"]["closed_since"] == "2024-12"


def test_direct_closed_place_detail_remains_auditable_with_original_and_operator_sources(client):
    http, data = client
    result = http.get("/api/pois/closed-museum")
    assert result.status_code == 200
    poi = result.json()["poi"]
    assert poi["operating_status"] == "closed" and poi["recommendable"] is False
    assert poi["source"] == data["pois"][0]["source"]
    assert poi["operating_status_source"] == data["pois"][0]["operating_status_source"]
    assert "raw_tags" not in poi


def test_closed_filter_precedes_category_totals_and_pagination(client):
    http, _ = client
    result = http.get("/api/pois", params={"category": "museum", "limit": 1}).json()
    assert result["total"] == 1 and result["pois"][0]["id"] == "active-museum"
    historical = http.get("/api/pois", params={"category": "museum", "include_closed": True, "offset": 1, "limit": 1}).json()
    assert historical["total"] == 2 and historical["pois"][0]["id"] == "active-museum"


@pytest.mark.parametrize("status", ["CLOSED", " Closed "])
def test_known_closed_status_handles_case_and_surrounding_whitespace(client, status):
    http, data = client
    data["pois"][0]["operating_status"] = status
    assert "closed-museum" not in {p["id"] for p in http.get("/api/pois").json()["pois"]}


def test_unrecognized_status_is_not_automatically_treated_as_closed(client):
    http, data = client
    data["pois"][0]["operating_status"] = "unverified"
    assert "closed-museum" in {p["id"] for p in http.get("/api/pois").json()["pois"]}
