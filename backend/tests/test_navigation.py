"""Street-routing contract and failure proof; these tests never use the network."""
import asyncio
import copy
import json
from collections import defaultdict, deque

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend import main, navigation
from backend.navigation import NavigationRequest, WalkingRouter, normalize_route


POINTS = [[71.43, 51.12], [71.4305, 51.1202], [71.431, 51.1205], [71.4315, 51.1205]]
SHAPE = "_wbo`B_vvfgCoKg^wQg^?g^"
SECOND_POINTS = [[71.4315, 51.1205], [71.432, 51.121], [71.433, 51.1215]]
SECOND_SHAPE = "gvco`BwsyfgCg^g^g^o}@"


def request(language="en", coordinates=None):
    return NavigationRequest(coordinates=coordinates or [POINTS[0], POINTS[-1]], language=language)


def provider_route(language="en-US"):
    return {"trip": {
        "status": 0, "units": "kilometers", "language": language,
        "summary": {"length": .12, "time": 95},
        "legs": [{
            "shape": SHAPE, "summary": {"length": .12, "time": 95},
            "maneuvers": [
                {"begin_shape_index": 0, "end_shape_index": 2, "travel_mode": "pedestrian",
                 "instruction": "Walk northeast.", "type": 1, "length": .085, "time": 65},
                {"begin_shape_index": 2, "end_shape_index": 3, "travel_mode": "pedestrian",
                 "instruction": "Turn right.", "type": 10, "length": .035, "time": 30},
                {"begin_shape_index": 3, "end_shape_index": 3, "travel_mode": "pedestrian",
                 "instruction": "You have arrived.", "type": 4, "length": 0, "time": 0},
            ],
        }],
    }}


@pytest.fixture
def mock_provider(monkeypatch):
    """Real HTTPX request/stream behavior with only the socket replaced."""
    original_client = httpx.AsyncClient

    def install(handler):
        transport = httpx.MockTransport(handler)
        monkeypatch.setattr(navigation.httpx, "AsyncClient",
                            lambda **kwargs: original_client(transport=transport, **kwargs))

    return install


@pytest.fixture
def api(monkeypatch):
    # Navigation does not require the recommendation graph or preference DB.
    # Avoid its unrelated startup and set only the state this endpoint owns.
    monkeypatch.setattr(main.app.state, "walking_router", WalkingRouter(), raising=False)
    monkeypatch.setattr(main, "_rate", defaultdict(deque))
    return TestClient(main.app)


def test_provider_shape_and_maneuvers_are_preserved(mock_provider, api):
    sent = []

    def respond(incoming):
        sent.append(incoming)
        return httpx.Response(200, json=provider_route())

    mock_provider(respond)
    response = api.post("/api/navigation/route", json=request().model_dump())
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    route = response.json()
    assert route["geometry"] == {"type": "LineString", "coordinates": POINTS}
    assert route["distance_m"] == 120 and route["duration_seconds"] == 95
    assert route["legs"][0]["steps"][1] == {
        "instruction": "Turn right.", "distance_m": 35, "duration_seconds": 30,
        "location": POINTS[2], "maneuver_type": 10,
        "geometry_start_index": 2, "geometry_end_index": 3,
    }
    assert route["provider"] == "Valhalla" and route["street_routed"] is True
    assert route["mode"] == "walking" and "OpenStreetMap" in route["attribution"]
    assert route["waypoints"][0]["snap_distance_m"] == 0
    assert len(sent) == 1 and str(sent[0].url) == navigation.DEFAULT_ROUTER_URL + "/route"
    outgoing = json.loads(sent[0].content)
    assert outgoing["costing"] == "pedestrian"
    assert outgoing["locations"] == [{"lon": lon, "lat": lat, "type": "break", "search_cutoff": 1000}
                                     for lon, lat in request().coordinates]
    assert outgoing["language"] == "en-US" and outgoing["units"] == "kilometers"
    assert sent[0].headers["X-Client-Id"]
    assert set(outgoing) == {"locations", "costing", "costing_options", "units", "language", "directions_type"}


@pytest.mark.parametrize("language,tag,instruction,fallback", [
    ("en", "en-US", "Walk northeast.", False),
    ("ru", "ru-RU", "Идите на северо-восток.", False),
    ("kk", "en-US", "Walk northeast.", True),
])
def test_narrative_language_and_explicit_kazakh_fallback(mock_provider, language, tag, instruction, fallback):
    body = provider_route(tag)
    body["trip"]["legs"][0]["maneuvers"][0]["instruction"] = instruction

    def respond(incoming):
        assert json.loads(incoming.content)["language"] == tag
        return httpx.Response(200, json=body)

    mock_provider(respond)
    route = asyncio.run(WalkingRouter().route(request(language)))
    assert route["language_requested"] == language
    assert route["language_used"] == ("ru" if language == "ru" else "en")
    assert route["language_fallback"] is fallback
    assert route["legs"][0]["steps"][0]["instruction"] == instruction
    assert bool(route["warnings"]) is fallback
    if fallback:
        assert "English" in route["warnings"][0]


@pytest.mark.parametrize("coordinates", [
    [], [POINTS[0]], [POINTS[0], POINTS[-1]] * 3,
    [[76.9, 43.2], POINTS[-1]], [[51.12, 71.43], POINTS[-1]],
    [[True, 51.12], POINTS[-1]], [["71.43", 51.12], POINTS[-1]],
    [[71.43, float("nan")], POINTS[-1]], [[float("inf"), 51.12], POINTS[-1]],
    [[10 ** 400, 51.12], POINTS[-1]], [[71.43], POINTS[-1]],
    [POINTS[0], POINTS[0]],
])
def test_input_is_bounded_before_any_provider_call(coordinates):
    with pytest.raises(ValidationError):
        request(coordinates=coordinates) if coordinates else NavigationRequest(coordinates=coordinates)


def test_endpoint_rejects_client_provider_urls_and_unknown_language(mock_provider, api):
    mock_provider(lambda _: pytest.fail("invalid input contacted provider"))
    for extra in ({"provider_url": "https://other.example"}, {"message": "secret conversation"}, {"language": "de"}):
        response = api.post("/api/navigation/route", json={**request().model_dump(), **extra})
        assert response.status_code == 422


@pytest.mark.parametrize("status,expected", [(400, 422), (404, 503), (429, 503), (500, 503), (302, 503)])
def test_provider_failures_never_return_a_synthetic_route(mock_provider, api, status, expected):
    mock_provider(lambda _: httpx.Response(status, json={"error": "provider failure"}, headers={"Location": "https://other.example"}))
    response = api.post("/api/navigation/route", json=request().model_dump())
    assert response.status_code == expected
    assert "geometry" not in response.json()
    if status == 429:
        assert response.headers["retry-after"] == "60"
    assert not main.app.state.walking_router.cache


def test_timeout_is_a_clear_service_unavailable_error(mock_provider, api):
    def timeout(incoming):
        raise httpx.ReadTimeout("provider timeout", request=incoming)

    mock_provider(timeout)
    response = api.post("/api/navigation/route", json=request().model_dump())
    assert response.status_code == 503
    assert "could not be reached" in response.json()["detail"]
    assert not main.app.state.walking_router.cache


@pytest.mark.parametrize("mutation", [
    lambda body: body.update(trip=[]),
    lambda body: body["trip"].update(legs=[None]),
    lambda body: body["trip"].update(summary=[]),
    lambda body: body["trip"].update(status=True),
    lambda body: body["trip"].update(units="miles"),
    lambda body: body["trip"].update(language="ru-RU"),
    lambda body: body["trip"]["summary"].update(length=50),
    lambda body: body["trip"]["legs"][0].update(shape="~"),
    lambda body: body["trip"]["legs"][0].update(maneuvers=[]),
    lambda body: body["trip"]["legs"][0].update(maneuvers=[[]]),
    lambda body: body["trip"]["legs"][0]["maneuvers"][0].update(begin_shape_index=999),
    lambda body: body["trip"]["legs"][0]["maneuvers"][0].update(travel_mode="drive"),
    lambda body: body["trip"]["legs"][0]["maneuvers"][0].update(instruction="\x00\x7f"),
    lambda body: body["trip"]["legs"][0]["maneuvers"][0].update(length=-1),
])
def test_invalid_provider_routes_are_rejected_and_not_cached(mock_provider, api, mutation):
    body = provider_route()
    mutation(body)
    mock_provider(lambda _: httpx.Response(200, json=body))
    response = api.post("/api/navigation/route", json=request().model_dump())
    assert response.status_code == 502
    assert "invalid route" in response.json()["detail"]
    assert not main.app.state.walking_router.cache


def test_response_size_limit_applies_while_streaming(mock_provider, api, monkeypatch):
    monkeypatch.setattr(navigation, "MAX_RESPONSE_BYTES", 100)
    mock_provider(lambda _: httpx.Response(200, content=b"x" * 101))
    response = api.post("/api/navigation/route", json=request().model_dump())
    assert response.status_code == 502


def test_multiple_legs_share_one_geometry_and_keep_global_maneuver_indices():
    body = provider_route()
    second = copy.deepcopy(body["trip"]["legs"][0])
    second["shape"] = SECOND_SHAPE
    second["maneuvers"] = [{**second["maneuvers"][0], "begin_shape_index": 0, "end_shape_index": 2}]
    body["trip"]["legs"].append(second)
    body["trip"]["summary"] = {"length": .24, "time": 190}
    route = normalize_route(body, request(coordinates=[POINTS[0], POINTS[-1], SECOND_POINTS[-1]]))
    assert route["geometry"]["coordinates"] == POINTS + SECOND_POINTS[1:]
    step = route["legs"][1]["steps"][0]
    assert step["geometry_start_index"] == 3 and step["geometry_end_index"] == 5
    assert step["location"] == POINTS[-1]
    assert len(route["waypoints"]) == 3 and route["distance_m"] == 240
    second["shape"] = "_hvo`B_x}ggCo}@o}@"
    with pytest.raises(ValueError, match="disconnected"):
        normalize_route(body, request(coordinates=[POINTS[0], POINTS[-1], SECOND_POINTS[-1]]))


def test_snapped_locations_are_disclosed_and_excessive_snap_is_rejected():
    moved = [71.428, 51.12]
    route = normalize_route(provider_route(), request(coordinates=[moved, POINTS[-1]]))
    assert route["waypoints"][0]["snap_distance_m"] > 75
    assert any("public entrance" in warning for warning in route["warnings"])
    with pytest.raises(ValueError, match="snapped too far"):
        normalize_route(provider_route(), request(coordinates=[[71.4, 51.1], POINTS[-1]]))


def test_cache_coalesces_concurrent_calls_copies_results_and_expires(mock_provider, monkeypatch):
    calls = []
    clock = [0.0]
    monkeypatch.setattr(navigation.time, "monotonic", lambda: clock[0])

    def respond(incoming):
        calls.append(incoming)
        return httpx.Response(200, json=provider_route())

    mock_provider(respond)

    async def exercise():
        router = WalkingRouter()
        first, second = await asyncio.gather(router.route(request()), router.route(request()))
        assert len(calls) == 1
        first["geometry"]["coordinates"][0][0] = 0
        assert second["geometry"]["coordinates"][0] == POINTS[0]
        assert (await router.route(request()))["geometry"]["coordinates"][0] == POINTS[0]
        clock[0] = 301
        await router.route(request())
        assert len(calls) == 2

    asyncio.run(exercise())


def test_route_endpoint_has_its_own_bounded_rate_limit(mock_provider, api):
    mock_provider(lambda _: httpx.Response(200, json=provider_route()))
    for _ in range(12):
        assert api.post("/api/navigation/route", json=request().model_dump()).status_code == 200
    response = api.post("/api/navigation/route", json=request().model_dump())
    assert response.status_code == 429 and response.headers["retry-after"] == "60"


@pytest.mark.parametrize("url", [
    "http://remote.example", "https://user:secret@router.example", "https://router.example?token=secret",
    "https://router.example#route", "file:///route", "https://router.example:invalid",
])
def test_operator_router_configuration_is_validated(url, monkeypatch):
    monkeypatch.setenv("QALA_VALHALLA_URL", url)
    with pytest.raises(ValueError):
        WalkingRouter()


def test_self_hosted_loopback_router_override(monkeypatch):
    monkeypatch.setenv("QALA_VALHALLA_URL", "http://127.0.0.1:8002/")
    assert WalkingRouter().url == "http://127.0.0.1:8002/route"
