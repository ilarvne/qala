"""Owned-key API audit tests never contact a provider or read real credentials."""
import json
from types import SimpleNamespace

import httpx
import pytest

from scripts.crawl_twogis_api import (
    ENDPOINT, MAX_BYTES, PROVIDER, ProviderFailure, fetch_diagnostics,
    identity_diagnostics, request_parameters, run_audit,
)
from scripts.providers.crawl_state import CrawlState


KEY = "test-secret-not-a-real-provider-key"
POI = {"id": "osm-node-123", "name": "Loom", "names": {"ru": "Лум"}, "lat": 51.1, "lon": 71.4, "name_derived": False}
OTHER = {"id": "osm-node-456", "name": "Other", "names": {}, "lat": 51.11, "lon": 71.41}
ITEM = {"id": "70000001012345678", "name": "Loom, a cafe", "name_ex": {"primary": "Loom"}, "type": "branch",
        "point": {"lat": 51.1, "lon": 71.4}, "reviews": {"general_rating": 4.9, "general_review_count": 101,
        "general_review_count_with_stars": 999, "items": [{"text": "Private review narrative", "author": "Private author"}]},
        "flags": {"photos": True}, "schedule": {"Mon": {"working_hours": [{"from": "09:00", "to": "22:00"}]}},
        "contact_groups": [{"contacts": [{"text": "Private provider contact"}]}]}


def payload(items=None, *, code=200, total=None):
    items = [ITEM] if items is None else items
    return {"meta": {"code": code}, "result": {"items": items, "total": len(items) if total is None else total}}


def clock_pair():
    tick = [1792512000.0]
    return lambda: tick[0], lambda seconds: tick.__setitem__(0, tick[0] + seconds)


def test_identity_uses_primary_name_and_exports_only_diagnostics():
    result = identity_diagnostics([ITEM], POI, [POI], total=1)
    assert result["identity_verified"]
    assert result["field_presence_counts"]["general_review_count_with_stars"] == 1
    encoded = json.dumps(result)
    for private in (ITEM["id"], "Loom", "Private review narrative", "Private author", "Private provider contact", "4.9", "999"):
        assert private not in encoded


def test_branch_ambiguity_cannot_be_resolved_by_nearest_result():
    second = {**ITEM, "id": "70000001012345679", "point": {"lat": 51.1001, "lon": 71.4001}}
    result = identity_diagnostics([ITEM, second], POI, [POI], total=2)
    assert result["identity_status"] == "ambiguous_identity" and not result["identity_verified"]
    duplicate = {**POI, "id": "osm-node-duplicate"}
    assert not identity_diagnostics([ITEM], POI, [POI, duplicate], total=1)["identity_verified"]


@pytest.mark.parametrize("point", [None, {"lat": 50, "lon": 70}, {"lat": True, "lon": 71.4}, {"lat": float("nan"), "lon": 71.4}])
def test_entity_coordinates_are_required_and_viewport_is_never_used(point):
    item = {**ITEM, "point": point, "geometry": {"centroid": {"lat": 51.1, "lon": 71.4}}}
    assert not identity_diagnostics([item], POI, [POI], total=1)["identity_verified"]


def test_truncated_or_missing_coordinate_branch_prevents_verified_identity():
    assert not identity_diagnostics([ITEM], POI, [POI], total=2)["identity_verified"]
    unseen = {**ITEM, "id": "70000001012345679", "point": None}
    assert not identity_diagnostics([ITEM, unseen], POI, [POI], total=2)["identity_verified"]


def test_official_request_is_name_bound_and_radius_uses_point():
    parameters = request_parameters(POI, KEY, "ru")
    assert parameters["q"] == "Лум, Астана"
    assert parameters["point"] == "71.4,51.1" and parameters["radius"] == 200
    assert "location" not in parameters and parameters["type"] == "branch"


def test_actual_run_is_resumable_without_product_storage_or_language_refetch(tmp_path):
    requests = []
    def respond(request):
        requests.append(request)
        assert request.url.host == "catalog.api.2gis.com" and request.url.path == "/3.0/items"
        assert request.url.params["key"] == KEY and "London" not in request.url.params["q"]
        return httpx.Response(200, json=payload())
    clock, sleep = clock_pair()
    output, state = tmp_path / "diagnostics.json", tmp_path / "private/state.json"
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        first = run_audit([{"poi_id": POI["id"], "query": "all cafes London"}], output, key=KEY, catalogue=[POI], state_path=state, client=client, clock=clock, sleep=sleep)
        second = run_audit([POI["id"]], output, key=KEY, catalogue=[POI], state_path=state, client=client, language="kk", clock=clock, sleep=sleep)
    assert len(requests) == 1 and second["new_queries"] == 0
    assert second["records"] == first["records"]
    assert not second["api_products_persisted"] and not second["crosswalk_persisted"]
    public_and_private = output.read_text() + state.read_text()
    for value in (KEY, ITEM["id"], "Private review narrative", "Private provider contact", "Loom, a cafe"):
        assert value not in public_and_private


@pytest.mark.parametrize("response", [httpx.Response(302, headers={"Location": "https://untrusted.invalid/?key=" + KEY}),
                                      httpx.Response(429, text=KEY),
                                      httpx.Response(200, json={"meta": {"code": 400, "error": {"message": KEY}}})])
def test_provider_error_stops_once_and_persists_before_next_network(tmp_path, response):
    calls = []
    clock, sleep = clock_pair()
    def respond(request):
        calls.append(request)
        return response
    output, state_path = tmp_path / "diagnostics.json", tmp_path / "private/state.json"
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        first = run_audit([POI["id"], OTHER["id"]], output, key=KEY, catalogue=[POI, OTHER], state_path=state_path, client=client, clock=clock, sleep=sleep)
        second = run_audit([POI["id"]], output, key=KEY, catalogue=[POI, OTHER], state_path=state_path, client=client, clock=clock, sleep=sleep)
    assert first["status"] == second["status"] == "provider_stopped"
    assert len(calls) == 1 and second["new_queries"] == 0
    assert KEY not in output.read_text() + state_path.read_text()


@pytest.mark.parametrize("headers", [{}, {"Content-Length": str(MAX_BYTES + 1)}])
def test_response_size_is_bounded_before_parsing(headers):
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, headers=headers, content=b"x" * (MAX_BYTES + 1)))) as client:
        with pytest.raises(ProviderFailure, match="response_too_large"):
            fetch_diagnostics(client, POI, [POI], KEY, "ru")


def test_transport_exception_never_serializes_key_or_private_request_url(tmp_path):
    def broken(request):
        raise httpx.ConnectError("secret " + KEY + " " + str(request.url), request=request)
    clock, sleep = clock_pair()
    output, state = tmp_path / "diagnostics.json", tmp_path / "state.json"
    with httpx.Client(transport=httpx.MockTransport(broken)) as client:
        result = run_audit([POI["id"]], output, key=KEY, catalogue=[POI], state_path=state, client=client, clock=clock, sleep=sleep)
    assert result["records"][0]["error_code"] == "transport_error"
    assert KEY not in output.read_text() + state.read_text()
    assert "?key=" not in state.read_text()


def test_public_captcha_stop_does_not_block_authorized_catalog_api(tmp_path):
    clock, sleep = clock_pair()
    state_path = tmp_path / "state.json"
    with CrawlState(state_path) as state:
        state.stop("captcha.2gis.ru", "captcha", "2026-10-20T10:00:00Z", source_url="https://captcha.2gis.ru/")
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload()))) as client:
        result = run_audit([POI["id"]], tmp_path / "diagnostics.json", key=KEY, catalogue=[POI], state_path=state_path, client=client, clock=clock, sleep=sleep)
    assert result["new_queries"] == 1
    with CrawlState(state_path) as state:
        assert state.is_stopped("2gis") and not state.is_stopped(PROVIDER)


def test_changed_local_seed_invalidates_only_its_completion_fingerprint(tmp_path):
    clock, sleep = clock_pair()
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=payload())
    output, state = tmp_path / "diagnostics.json", tmp_path / "state.json"
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        run_audit([POI["id"]], output, key=KEY, catalogue=[POI], state_path=state, client=client, clock=clock, sleep=sleep)
        changed = {**POI, "lat": 51.1001}
        result = run_audit([POI["id"]], output, key=KEY, catalogue=[changed], state_path=state, client=client, clock=clock, sleep=sleep)
    assert len(requests) == 2 and len(result["records"]) == 2
    assert result["records"][0]["observed_at"] != result["records"][1]["observed_at"]


def test_query_cap_and_pacing_are_enforced_with_a_fake_clock(tmp_path):
    clock, sleep = clock_pair()
    starts = []
    def respond(request):
        starts.append(clock())
        return httpx.Response(200, json=payload())
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = run_audit([POI["id"], OTHER["id"]], tmp_path / "d.json", key=KEY, catalogue=[POI, OTHER], state_path=tmp_path / "s.json", client=client, clock=clock, sleep=sleep, delay_seconds=1)
    assert len(starts) == 2 and starts[1] - starts[0] >= 1
    assert result["new_queries"] == 2
    with httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("Invalid bulk request must not start"))) as client:
        with pytest.raises(ValueError):
            run_audit([POI["id"]] * 21, tmp_path / "x.json", key=KEY, catalogue=[POI], state_path=tmp_path / "xx.json", client=client)


def test_one_query_limit_retains_atomic_partial_progress(tmp_path):
    clock, sleep = clock_pair()
    calls = []
    with httpx.Client(transport=httpx.MockTransport(lambda request: calls.append(request) or httpx.Response(200, json=payload()))) as client:
        result = run_audit([POI["id"], OTHER["id"]], tmp_path / "diagnostics.json", key=KEY, catalogue=[POI, OTHER], state_path=tmp_path / "state.json", client=client, clock=clock, sleep=sleep, limit=1)
    assert result["status"] == "partial" and len(calls) == 1
    assert json.loads((tmp_path / "diagnostics.json").read_text())["records"] == result["records"]


def test_explicitly_empty_environment_disables_private_dotenv_key_before_any_client(monkeypatch, tmp_path):
    import scripts.crawl_twogis_api as audit
    (tmp_path / "data").mkdir()
    (tmp_path / "data/pois.json").write_text(json.dumps({"pois": [POI]}))
    seeds, output, state = tmp_path / "seeds.json", tmp_path / "diagnostics.json", tmp_path / "state.json"
    seeds.write_text(json.dumps([POI["id"]]))
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    monkeypatch.setattr(audit, "dotenv_values", lambda *_, **__: {"TWOGIS_API_KEY": "private-file-key-that-must-stay-disabled"})
    monkeypatch.setenv("TWOGIS_API_KEY", "")
    monkeypatch.setattr("sys.argv", ["audit", "--seeds", str(seeds), "--out", str(output), "--state", str(state)])
    monkeypatch.setattr(audit.httpx, "Client", lambda *_, **__: pytest.fail("Explicit empty environment must prevent client creation despite a populated .env"))
    with pytest.raises(SystemExit) as result:
        audit.main()
    assert result.value.code == 2
    assert not output.exists() and not state.exists()
