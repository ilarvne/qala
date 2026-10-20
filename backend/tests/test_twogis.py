"""Owned-key source lookups must remain bounded, separate and evidence-specific."""
import asyncio
import copy
import json
from collections import defaultdict, deque

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.twogis import TwoGIS, CROSSWALK, LOCALES


SECRET = "private-2gis-fixture-key"
MUSEUM = {"id": "osm-node-4894937300", "name": "National Museum of the Republic of Kazakhstan",
          "names": {"ru": "Национальный музей Республики Казахстан"}, "lat": 51.1182297, "lon": 71.4693823,
          "source": {"url": "https://www.openstreetmap.org/node/4894937300"}}
CAFE = {"id": "local-cafe", "name": "Exact café", "names": {"ru": "Точная кофейня"},
        "lat": 51.128, "lon": 71.43, "address": "Public street, 1"}


def profile(identifier="70000001018608940", name="Национальный музей РК", lat=51.118023, lon=71.469471):
    return {"id": identifier, "name": name, "point": {"lat": lat, "lon": lon}, "address_name": "Public street, 1",
            "reviews": {"general_rating": 5, "general_review_count": 20, "general_review_count_with_stars": 100,
                        "org_rating": 4.2, "org_review_count": 25, "org_review_count_with_stars": 99,
                        "items": [{"text": "Never export this review", "author": "Never export author"}]},
            "flags": {"photos": True},
            "schedule": {"Tue": {"working_hours": [{"from": "10:00", "to": "18:00"}]}, "comment": "Operator ticket-office comment"},
            "rubrics": [{"id": "193", "name": "Музеи"}]}


def payload(items):
    return {"meta": {"code": 200}, "result": {"items": items, "total": len(items)}}


class Clock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps = []
    def __call__(self):
        return self.now
    async def sleep(self, delay):
        self.sleeps.append(delay)
        self.now += delay


def service(handler, **kwargs):
    clock = kwargs.pop("clock", Clock())
    return TwoGIS(key=SECRET, transport=httpx.MockTransport(handler), clock=clock, sleep=clock.sleep, **kwargs), clock


def test_no_key_closed_and_derived_places_never_spend_a_request():
    def forbidden(request):
        pytest.fail("No provider request should occur")
    async def run():
        provider = TwoGIS(key="", transport=httpx.MockTransport(forbidden))
        assert (await provider.lookup(MUSEUM))["status"] == "key_required"
        assert provider.status()["checked_at"] is None
        await provider.close()
        provider, _ = service(forbidden)
        assert (await provider.lookup({**CAFE, "operating_status": "closed"}))["reason"] == "local_closed"
        assert (await provider.lookup({**CAFE, "operating_status": " CLOSED "}))["reason"] == "local_closed"
        assert (await provider.lookup({**CAFE, "name_derived": True}))["reason"] == "local_identity_missing"
        assert not provider.status()["live_verified"]
        await provider.close()
    asyncio.run(run())


@pytest.mark.parametrize("language", ["ru", "en", "kk"])
def test_owned_lookup_uses_exact_known_id_and_correct_locale(language):
    requests = []
    def respond(request):
        requests.append(request)
        assert request.url.host == "catalog.api.2gis.com" and request.url.path == "/3.0/items/byid"
        assert request.url.params["id"] == CROSSWALK[MUSEUM["id"]]["provider_id"]
        assert request.url.params["locale"] == LOCALES[language]
        assert request.url.params["key"] == SECRET and "page_size" not in request.url.params
        assert "items.contact_groups" in request.url.params["fields"]
        return httpx.Response(200, json=payload([profile()]))
    async def run():
        provider, _ = service(respond)
        assert provider.status()["configured"] and not provider.status()["live_verified"]
        result = await provider.lookup(MUSEUM, language)
        assert result["status"] == "matched" and result["source"]["provider_id"] == "70000001018608940"
        assert provider.status()["live_verified"] and provider.status()["checked_at"] == result["checked_at"]
        assert SECRET not in json.dumps(result) and len(requests) == 1
        await provider.close()
    asyncio.run(run())


def test_general_and_org_statistics_remain_independent_and_prose_is_excluded():
    async def run():
        provider, _ = service(lambda _: httpx.Response(200, json=payload([profile()])))
        result = await provider.lookup(MUSEUM)
        source = result["source"]
        assert (source["rating"], source["rating_count"], source["review_count"]) == (5, 100, 20)
        assert source["native_statistics"]["org_rating"] == 4.2
        assert source["native_statistics"]["org_review_count"] == 25
        assert source["has_photos"] is True and source["contacts"] == []
        assert source["route_url"] is None and source["schedule_special"] is None
        assert source["photo_gallery_url"] == source["url"] + "/tab/photos"
        assert source["review_url"] == source["url"] + "/tab/reviews"
        assert all(text not in json.dumps(result) for text in ["Never export", "author", "items"])
        await provider.close()
    asyncio.run(run())


def test_missing_general_values_do_not_fall_back_to_org_or_zero():
    item = profile(); item["reviews"] = {"org_rating": 4.2, "org_review_count": 20, "org_review_count_with_stars": 100}
    async def run():
        provider, _ = service(lambda _: httpx.Response(200, json=payload([item])))
        source = (await provider.lookup(MUSEUM))["source"]
        assert source["rating"] is None and source["review_count"] is None and source["rating_count"] is None
        await provider.close()
    asyncio.run(run())


def test_generic_search_is_public_place_only_and_matches_exact_alias_and_point():
    requests = []
    def respond(request):
        requests.append(request)
        assert request.url.path == "/3.0/items" and request.url.params["page_size"] == "5"
        assert request.url.params["q"] == "Точная кофейня Public street, 1"
        assert request.url.params["point"] == "71.43,51.128" and request.url.params["radius"] == "200"
        assert all(value not in str(request.url) for value in ["session", "user_location", "message"])
        item = profile("70000001012345678", "Точная кофейня, кафе", CAFE["lat"], CAFE["lon"])
        item["name_ex"] = {"primary": "Точная кофейня", "extension": "кафе"}
        return httpx.Response(200, json=payload([item]))
    async def run():
        provider, _ = service(respond)
        before = copy.deepcopy(CAFE)
        assert (await provider.lookup(CAFE))["status"] == "matched" and CAFE == before
        assert len(requests) == 1
        await provider.close()
    asyncio.run(run())


@pytest.mark.parametrize("problem", ["wrong_name", "far", "same_name_branches", "known_wrong_id"])
def test_identity_uncertainty_is_not_a_forced_match(problem):
    target = MUSEUM if problem == "known_wrong_id" else CAFE
    item = profile("70000001012345678", "Exact café", CAFE["lat"], CAFE["lon"])
    if problem == "wrong_name": item["name"] = "Another café"
    if problem == "far": item["point"]["lat"] += .01
    if problem == "known_wrong_id": item["point"] = {"lat": MUSEUM["lat"], "lon": MUSEUM["lon"]}; item["name"] = MUSEUM["name"]
    items = [item, {**copy.deepcopy(item), "id": "70000001012345679"}] if problem == "same_name_branches" else [item]
    async def run():
        provider, _ = service(lambda _: httpx.Response(200, json=payload(items)))
        result = await provider.lookup(target)
        assert result["status"] == "ambiguous" and result["source"] is None and result["candidates"]
        assert "distance_m" in result["candidates"][0]
        await provider.close()
    asyncio.run(run())


def test_reused_or_relocated_known_local_identity_does_not_get_curated_byid():
    requests = []
    def respond(request):
        requests.append(request)
        assert request.url.path == "/3.0/items" and "id" not in request.url.params
        return httpx.Response(200, json=payload([]))
    async def run():
        provider, _ = service(respond)
        await provider.lookup({**MUSEUM, "lat": MUSEUM["lat"] + .02})
        await provider.lookup({**MUSEUM, "source": {"url": "https://example.org/reused"}})
        assert len(requests) == 2
        await provider.close()
    asyncio.run(run())


@pytest.mark.parametrize("problem", ["larger_total", "oversized_page", "full_page_without_total"])
def test_generic_truncated_candidates_never_establish_a_unique_identity(problem):
    selected = profile("70000001012345678", CAFE["name"], CAFE["lat"], CAFE["lon"])
    unrelated = [profile("7000000101234568" + str(index), "Another business", CAFE["lat"], CAFE["lon"]) for index in range(5)]
    result = payload([selected, *unrelated[:4]])
    if problem == "larger_total": result["result"]["total"] = 6
    elif problem == "oversized_page": result = payload([selected, *unrelated])
    else: del result["result"]["total"]
    async def run():
        provider, _ = service(lambda _: httpx.Response(200, json=result))
        response = await provider.lookup(CAFE)
        assert response["status"] == "ambiguous" and response["source"] is None
        assert response["reason"] == ("result_completeness_unknown" if problem == "full_page_without_total" else "result_truncated")
        assert len(response["candidates"]) <= 5
        await provider.close()
    asyncio.run(run())


@pytest.mark.parametrize("missing", [None, {"lat": 51.128}, {"lat": 99, "lon": 71.43}])
def test_same_name_candidate_without_valid_point_prevents_forced_branch_match(missing):
    first = profile("70000001012345678", CAFE["name"], CAFE["lat"], CAFE["lon"])
    second = {**profile("70000001012345679", "Exact café, cafe"), "point": missing,
              "name_ex": {"primary": CAFE["name"], "extension": "cafe"}}
    async def run():
        provider, _ = service(lambda _: httpx.Response(200, json=payload([first, second])))
        response = await provider.lookup(CAFE)
        assert response["status"] == "ambiguous" and response["source"] is None
        assert response["reason"] == "candidate_coordinates_missing"
        assert [row["provider_id"] for row in response["candidates"]] == [first["id"]]
        await provider.close()
    asyncio.run(run())


def test_missing_point_only_reports_not_found_with_reason_and_no_invented_geometry():
    item = profile("70000001012345678", CAFE["name"]); item.pop("point")
    async def run():
        provider, _ = service(lambda _: httpx.Response(200, json=payload([item])))
        response = await provider.lookup(CAFE)
        assert response["status"] == "not_found" and response["source"] is None and response["candidates"] == []
        assert response["reason"] == "candidate_coordinates_missing"
        await provider.close()
    asyncio.run(run())


def test_known_byid_remains_exact_even_when_general_result_metadata_is_larger():
    result = payload([profile()]); result["result"]["total"] = 100
    async def run():
        provider, _ = service(lambda _: httpx.Response(200, json=result))
        assert (await provider.lookup(MUSEUM))["status"] == "matched"
        await provider.close()
    asyncio.run(run())


def test_concurrent_requests_share_one_inflight_but_completed_profiles_are_not_cached():
    requests = []
    async def respond(request):
        requests.append(request)
        await asyncio.sleep(0)
        return httpx.Response(200, json=payload([profile()]))
    async def run():
        provider, clock = service(respond)
        results = await asyncio.gather(*(provider.lookup(MUSEUM) for _ in range(5)))
        assert len(requests) == 1 and sum(item["coalesced"] for item in results) == 4
        results[0]["source"]["name"] = "Mutation"
        assert all(item["source"]["name"] != "Mutation" for item in results[1:])
        await provider.lookup(MUSEUM)
        assert len(requests) == 2 and clock.sleeps == [1]
        await provider.close()
    asyncio.run(run())


def test_failed_new_request_never_reuses_old_profile():
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=payload([profile()])) if len(requests) == 1 else httpx.Response(503)
    async def run():
        provider, clock = service(respond)
        assert (await provider.lookup(MUSEUM))["status"] == "matched"
        result = await provider.lookup(MUSEUM)
        assert result["status"] == "unavailable" and result["source"] is None and len(requests) == 2
        await provider.close()
    asyncio.run(run())


def test_httpx_info_logs_do_not_expose_server_query_key(caplog):
    async def run():
        provider, _ = service(lambda _: httpx.Response(200, json=payload([profile()])))
        with caplog.at_level("INFO", logger="httpx"):
            await provider.lookup(MUSEUM)
        assert SECRET not in caplog.text and "redacted" in caplog.text
        await provider.close()
    asyncio.run(run())


@pytest.mark.parametrize("problem", ["http401", "http403", "http429", "redirect", "meta400", "body", "transport"])
def test_provider_failures_are_sanitized_and_not_retried(problem):
    requests = []
    def respond(request):
        requests.append(request)
        if problem == "transport": raise httpx.ConnectError(str(request.url))
        if problem.startswith("http"): return httpx.Response(int(problem[4:]), text=SECRET)
        if problem == "redirect": return httpx.Response(302, headers={"Location": "https://unrelated.example/?key=" + SECRET})
        if problem == "meta400": return httpx.Response(200, json={"meta": {"code": 400, "error": {"message": SECRET}}})
        return httpx.Response(200, content=b"x" * 1_000_001)
    async def run():
        provider, _ = service(respond)
        result = await provider.lookup(MUSEUM)
        assert result["status"] == "unavailable" and result["source"] is None and len(requests) == 1
        assert SECRET not in json.dumps(result) and not provider.status()["live_verified"]
        if problem in {"http401", "http403", "http429"}:
            await provider.lookup(CAFE)
            assert len(requests) == 1
        await provider.close()
    asyncio.run(run())


def test_request_budget_and_request_start_interval_apply_across_places_and_languages():
    requests = []
    async def run():
        clock = Clock()
        def respond(request):
            requests.append(clock.now)
            return httpx.Response(200, json=payload([]))
        provider, _ = service(respond, clock=clock, request_budget=2)
        await provider.lookup(MUSEUM, "ru")
        await provider.lookup(CAFE, "en")
        result = await provider.lookup(CAFE, "kk")
        assert requests == [1000, 1001] and result["status"] == "unavailable"
        assert result["reason"] == "request_budget_exhausted" and provider.status()["budget_remaining"] == 0
        await provider.close()
    asyncio.run(run())


def test_contacts_schedule_and_statistics_are_allowlisted_and_invalid_values_stay_unknown():
    item = profile()
    item["reviews"]["general_rating"] = float("nan")
    item["reviews"]["general_review_count_with_stars"] = True
    item["flags"]["photos"] = "yes"
    item["schedule"]["Mon"] = {"working_hours": [{"from": "25:00", "to": "26:00"}]}
    item["contact_groups"] = [{"contacts": [{"type": "website", "value": "Operator website", "url": "https://operator.example/"},
                                             {"type": "phone", "value": "+7 700 000 00 00", "url": "http://127.0.0.1/"},
                                             {"type": "website", "value": SECRET, "url": "https://operator.example/?key=" + SECRET}]}]
    # JSON's NaN extension is intentionally malformed source data; parser must
    # reject the value, not turn it into a zero or an invalid output number.
    async def run():
        provider, _ = service(lambda _: httpx.Response(200, content=json.dumps(payload([item])).encode()))
        source = (await provider.lookup(MUSEUM))["source"]
        assert source["rating"] is None and source["rating_count"] is None and source["has_photos"] is None
        assert source["schedule"]["Mon"]["working_hours"] == []
        assert len(source["contacts"]) == 2 and source["contacts"][1]["url"] is None
        assert SECRET not in json.dumps(source) and "http://127" not in json.dumps(source)
        await provider.close()
    asyncio.run(run())


def test_source_endpoint_is_no_store_rate_limited_and_reports_current_process_verification(monkeypatch, tmp_path):
    import backend.main as main
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=payload([profile()]))
    provider, _ = service(respond)
    monkeypatch.setattr(main, "TwoGIS", lambda: provider)
    monkeypatch.setattr(main, "_rate", defaultdict(deque))
    monkeypatch.setenv("QALA_MEMORY_PATH", str(tmp_path / "memory.sqlite3"))
    with TestClient(main.app) as client:
        before = {item["id"]: item for item in client.get("/api/integrations").json()["integrations"]}
        assert before["twogis"]["status"] == "configured" and not before["twogis"]["live_verified"]
        response = client.get(f"/api/pois/{MUSEUM['id']}/sources/2gis?language=ru")
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert response.json()["status"] == "matched" and len(calls) == 1
        after = {item["id"]: item for item in client.get("/api/integrations").json()["integrations"]}
        assert after["twogis"]["status"] == "active" and after["twogis"]["live_verified"]
        assert SECRET not in json.dumps(after)
        assert client.get(f"/api/pois/{MUSEUM['id']}/sources/2gis?language=bad").status_code == 422
        assert client.get("/api/pois/missing/sources/2gis").status_code == 404
        # Unknown IDs consume the same per-IP route budget without issuing API calls.
        for _ in range(28):
            assert client.get("/api/pois/missing/sources/2gis").status_code == 404
        assert client.get("/api/pois/missing/sources/2gis").status_code == 429
        assert len(calls) == 1
