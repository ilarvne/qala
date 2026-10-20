"""External context must be factual, time-specific, private and fail open."""
import asyncio
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from backend import events, weather, alemplus
from backend.agent import CityAgent
from backend.context import resolve_constraints
from backend.events import OfficialEvents, parse_calendar
from backend.main import app
from backend.memory import PreferenceMemory
from backend.models import ConversationContext, EventsContext, RecommendRequest
from backend.weather import CityWeather

LOCAL = ZoneInfo("Asia/Almaty")


def start():
    return datetime.now(LOCAL).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def forecast_payload(at, hours=5):
    return {"hourly_units": {"time": "unixtime", "temperature_2m": "°C", "apparent_temperature": "°C", "wind_speed_10m": "km/h",
                             "wind_gusts_10m": "km/h", "precipitation": "mm", "precipitation_probability": "%", "weather_code": "wmo code", "is_day": ""},
            "hourly": {"time": [int((at + timedelta(hours=index)).timestamp()) for index in range(hours)],
                       "temperature_2m": [10] * hours, "apparent_temperature": [8] * hours, "wind_speed_10m": [5] * hours,
                       "wind_gusts_10m": [10] * hours, "precipitation": [0] * hours, "precipitation_probability": [0] * hours,
                       "weather_code": [0] * hours, "is_day": [1] * hours}}


def install_forecast(monkeypatch, payload, capture=None):
    monkeypatch.setenv("QALA_WEATHER", "on")
    async def get(url, **kwargs):
        if capture is not None:
            capture.append((url, kwargs))
        return json.dumps(payload).encode()
    monkeypatch.setattr(weather, "public_get", get)


def test_weather_uses_planned_hour_and_entire_visit_not_current_weather(monkeypatch):
    at = start()
    payload = forecast_payload(at)
    payload["hourly"]["apparent_temperature"][2] = -15
    payload["hourly"]["wind_gusts_10m"][2] = 65
    payload["hourly"]["precipitation"][2] = 2
    payload["hourly"]["weather_code"][2] = 95
    install_forecast(monkeypatch, payload)
    result = asyncio.run(CityWeather().forecast(at + timedelta(minutes=30), 90, language="ru"))
    assert result.status == "available" and result.valid_at == (at + timedelta(minutes=30)).isoformat()
    assert set(result.reason_codes) == {"cold", "wind", "precipitation", "thunderstorm"}
    assert result.gust_kmh == 65 and result.precipitation_mm == 2
    assert result.apparent_temperature_c == 8
    assert any("гроза" in guidance for guidance in result.guidance)


def test_external_weather_payload_contains_only_fixed_city_coordinates(monkeypatch):
    capture = []
    at = start()
    install_forecast(monkeypatch, forecast_payload(at), capture)
    result = asyncio.run(CityWeather().forecast(at, 30))
    assert result.status == "available"
    params = capture[0][1]["params"]
    assert (params["latitude"], params["longitude"]) == weather.CITY
    assert set(params) == {"latitude", "longitude", "hourly", "timezone", "timeformat", "wind_speed_unit", "forecast_days", "past_days"}
    assert "session" not in json.dumps(capture) and "message" not in json.dumps(capture)


def test_parallel_forecasts_coalesce_and_return_separate_immutable_results(monkeypatch):
    at, calls = start(), []
    install_forecast(monkeypatch, forecast_payload(at), calls)
    async def run():
        provider = CityWeather()
        return await asyncio.gather(*(provider.forecast(at, 60) for _ in range(4)))
    results = asyncio.run(run())
    assert len(calls) == 1 and sum(not item.cached for item in results) == 1
    results[0].guidance.append("test mutation")
    assert all("test mutation" not in item.guidance for item in results[1:])


@pytest.mark.parametrize("mutation", ["units", "missing", "nonfinite", "time_gap", "daylight"])
def test_invalid_weather_never_becomes_zero_or_live_verified(monkeypatch, mutation):
    at = start()
    payload = forecast_payload(at)
    if mutation == "units": payload["hourly_units"]["wind_speed_10m"] = "mph"
    if mutation == "missing": payload["hourly"]["precipitation"][1] = None
    if mutation == "nonfinite": payload["hourly"]["temperature_2m"][0] = float("nan")
    if mutation == "time_gap": payload["hourly"]["time"][2] += 1800
    if mutation == "daylight": payload["hourly"]["is_day"][1] = .5
    install_forecast(monkeypatch, payload)
    provider = CityWeather()
    result = asyncio.run(provider.forecast(at, 60))
    assert result.status == "unavailable" and result.temperature_c is None and not result.reason_codes
    assert provider.status()["live_verified"] is False


def test_failed_refresh_discards_expired_forecast(monkeypatch):
    at = start()
    install_forecast(monkeypatch, forecast_payload(at))
    provider = CityWeather()
    assert asyncio.run(provider.forecast(at, 60)).status == "available"
    provider._expires = 0
    async def fail(*args, **kwargs): raise TimeoutError("private upstream error")
    monkeypatch.setattr(weather, "public_get", fail)
    result = asyncio.run(provider.forecast(at, 60))
    assert result.status == "unavailable" and result.fetched_at is None
    assert "private" not in result.model_dump_json()


def test_disabled_outside_city_and_outside_horizon_never_make_requests(monkeypatch):
    async def forbidden(*args, **kwargs): pytest.fail("No external lookup should occur")
    monkeypatch.setattr(weather, "public_get", forbidden)
    provider, at = CityWeather(), start()
    assert asyncio.run(provider.forecast(at, 60)).status == "disabled"
    monkeypatch.setenv("QALA_WEATHER", "on")
    assert asyncio.run(provider.forecast(at, 60, in_city=False)).status == "outside_city"
    assert asyncio.run(provider.forecast(at + timedelta(days=40), 60)).status == "outside_forecast"


def calendar_html(stamp="28 октября 2026", url="https://a-vm.kz/events/source-event/", title="Source event"):
    return f'<div class="news-cardx"><a class="news-card__link" href="{url}">{title}</a><div class="news-card__date">{stamp}</div></div>'


def test_event_parser_does_not_invent_times_locations_or_use_publication_dates():
    html = '<time datetime="2026-11-01">Published</time>' + calendar_html(title="Opera &amp; music")
    item = parse_calendar(html)[0]
    assert item.date == "2026-10-28" and item.title == "Opera & music"
    assert item.start_time is None and item.venue is None and item.poi_id is None
    assert item.availability == "unverified" and item.date_precision == "day"


@pytest.mark.parametrize("stamp,url", [("31 февраля 2026", "https://a-vm.kz/events/x/"), ("28 октября", "https://a-vm.kz/events/x/"),
    ("28 октября 2026", "https://a-vm.kz.evil.example/events/x/"), ("28 октября 2026", "javascript:alert(1)"),
    ("28 октября 2026", "https://a-vm.kz/events/x/?secret=x")])
def test_calendar_rejects_ambiguous_dates_or_untrusted_links(stamp, url):
    assert parse_calendar(calendar_html(stamp=stamp, url=url)) == []


def test_calendar_respects_robots_before_fetching_metadata(monkeypatch):
    monkeypatch.setenv("QALA_EVENTS", "on")
    calls = []
    async def get(url, **kwargs):
        calls.append(url)
        assert url == events.ROBOTS_URL
        return b"User-agent: *\nDisallow: /events/\n"
    monkeypatch.setattr(events, "public_get", get)
    provider = OfficialEvents()
    result = asyncio.run(provider.upcoming(start()))
    assert result.status == "unavailable" and not result.items
    assert calls == [events.ROBOTS_URL] and not provider.status()["live_verified"]


def test_calendar_filters_selected_days_and_caches_public_metadata(monkeypatch):
    monkeypatch.setenv("QALA_EVENTS", "on")
    calls = []
    async def get(url, **kwargs):
        calls.append(url)
        return b"User-agent: *\nAllow: /\n" if url == events.ROBOTS_URL else (calendar_html() + calendar_html(stamp="18 октября 2026", url="https://a-vm.kz/events/past/")).encode()
    monkeypatch.setattr(events, "public_get", get)
    provider = OfficialEvents()
    at = datetime(2026, 10, 20, 14, tzinfo=LOCAL)
    result = asyncio.run(provider.upcoming(at))
    same_day = asyncio.run(provider.upcoming(at, days=1))
    assert result.status == "available" and [item.date for item in result.items] == ["2026-10-28"]
    assert same_day.status == "available" and same_day.items == [] and same_day.cached
    assert len(calls) == 2


def test_broken_calendar_markup_is_unavailable_not_an_empty_city(monkeypatch):
    monkeypatch.setenv("QALA_EVENTS", "on")
    async def get(url, **kwargs):
        return b"User-agent: *\nAllow: /\n" if url == events.ROBOTS_URL else b"<html><h1>Calendar changed</h1></html>"
    monkeypatch.setattr(events, "public_get", get)
    assert asyncio.run(OfficialEvents().upcoming(start())).status == "unavailable"


def poi(identifier, category, indoor, score=.8):
    return {"id": identifier, "name": identifier, "category": category, "description": "Public source record", "tags": [], "lat": 51.1282, "lon": 71.4304,
            "source": {"url": "https://www.openstreetmap.org/node/1", "collected_at": "2026-10-20"}, "indoor": indoor, "hours": "24/7", "wheelchair": "yes",
            "retrieval_score": score, "distance_m": 10}


@pytest.fixture
def tiny_agent(tmp_path):
    return CityAgent({"metadata": {"count": 2, "collected_at": "2026-10-20", "attribution": "OpenStreetMap"},
                      "pois": [poi("indoor", "museum", True, .65), poi("outdoor", "park", False, .8)]}, PreferenceMemory(tmp_path / "preferences.sqlite3"))


def test_adverse_weather_softly_prefers_shelter_but_does_not_override_outdoors(tiny_agent):
    request = RecommendRequest(message="Anything nearby", duration_minutes=45, location={"lat": 51.1282, "lon": 71.4304})
    state = tiny_agent.context({"request": request.model_dump(), "trace": []})
    state["context"].update(weather={"reason_codes": ["wind"]}, weather_effect={"applied": False, "strategy": "none", "reason_codes": ["wind"], "explicit_outdoor_request": False})
    state["candidates"] = tiny_agent.retriever.pois
    result = tiny_agent.plan(state)
    assert result["recommendations"][0]["id"] == "indoor" and result["context"]["weather_effect"]["applied"]
    state["context"]["weather_effect"]["explicit_outdoor_request"] = True
    explicit = tiny_agent.plan(state)
    assert explicit["recommendations"][0]["id"] == "outdoor" and not explicit["context"]["weather_effect"]["applied"]


def test_event_request_replaces_sticky_coffee_and_tomorrow_survives_followup():
    at = datetime(2026, 10, 20, 14, tzinfo=LOCAL)
    request = RecommendRequest(message="Какие мероприятия завтра?", interests=["coffee"], starts_at=at,
                               conversation={"interests": ["coffee"], "duration_minutes": 90})
    context = resolve_constraints(request, None, set())
    assert context["interests"] == ["events"] and context["event_date"] == "2026-10-21"
    next_request = RecommendRequest(message="А 2026-10-28?", starts_at=at, conversation={key: value for key, value in context.items() if key in ConversationContext.model_fields})
    following = resolve_constraints(next_request, None, set())
    assert following["event_date"] == "2026-10-28" and following["interests"] == ["events"]


def test_event_graph_returns_dated_sources_without_making_up_a_walking_stop(tiny_agent, monkeypatch):
    async def upcoming(at, **kwargs):
        return EventsContext(status="available", requested_date=at.date().isoformat(), fetched_at="2026-10-20T09:00:00Z",
                             items=[{"id": "source-event", "title": "Source event", "url": "https://a-vm.kz/events/source-event/", "date": "2026-10-28"}])
    monkeypatch.setattr(tiny_agent.events, "upcoming", upcoming)
    result = asyncio.run(tiny_agent.recommend(RecommendRequest(message="Какие события в Астане?", language="ru")))
    assert result["events"][0]["title"] in result["message"]
    assert result["recommendations"] == [] and result["route"]["coordinates"] == []
    assert result["sources"][0]["url"] == "https://a-vm.kz/events/source-event/"
    assert not result["clarifications"] and any(step["node"] == "event_response" for step in result["trace"])
    assert not any(step["node"] == "hybrid_retrieval" for step in result["trace"])


def test_provider_failure_keeps_a_grounded_walking_plan(tiny_agent):
    result = asyncio.run(tiny_agent.recommend(RecommendRequest(message="A museum nearby", duration_minutes=90,
                               location={"lat": 51.1282, "lon": 71.4304}, starts_at=start())))
    assert result["recommendations"] and result["context"]["weather"]["status"] == "disabled"
    assert result["context"]["events"]["status"] == "disabled" and result["route"]["total_minutes"] <= 90


def test_integrations_separates_configuration_from_verification_and_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("QALA_MEMORY_PATH", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("ALEMPLUS_API_KEY", "private-fixture-key")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "private-fixture-eleven")
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", "private-fixture-agent")
    monkeypatch.setattr(alemplus, "_status", {})
    with TestClient(app) as client:
        response = client.get("/api/integrations")
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        values = {item["id"]: item for item in response.json()["integrations"]}
        assert values["llm"]["status"] == "configured" and not values["llm"]["live_verified"]
        assert values["elevenlabs_agent"]["status"] == "configured" and values["google_places"]["status"] == "restricted"
        assert values["foursquare"]["status"] == "not_integrated" and values["weather"]["status"] == "disabled"
        assert all(secret not in response.text for secret in ("private-fixture-key", "private-fixture-eleven", "private-fixture-agent"))


@pytest.mark.parametrize("message,expected", [
    ("Only indoors, not outdoors", True),
    ("Not outside, only indoors", True),
    ("Только в помещении, не на улице", True),
    ("Жабық жерде, ашық ауада емес", True),
    ("Outside please", False),
    ("На свежем воздухе", False),
    ("Ашық ауада", False),
    ("Not indoors, outdoors instead", False),
    ("Не в помещении, на улице", False),
    ("Ашық ауада, жабық жерде емес", False),
    ("Not only indoors", False),
    ("Не только в помещении", False),
])
def test_shared_environment_negation_preserves_explicit_precedence(message, expected):
    from backend.context import resolve_environment
    request = RecommendRequest(message=message, indoor=not expected,
                               conversation={"indoor": not expected, "outdoor_preference": expected})
    resolved = resolve_constraints(request, None, set())
    environment = resolve_environment(message)
    assert resolved["indoor"] is expected
    assert environment["indoor"] is expected
    assert not (resolved["indoor"] and resolved["outdoor_preference"])
    assert ("indoor" in resolved["interests"]) is expected


@pytest.mark.parametrize("message", [
    "Recommend nearby places using the selected preferences.",
    "Suggest something nearby",
    "Подбери места рядом с учетом выбранных настроек.",
    "Посоветуй что-нибудь поблизости",
    "Таңдалған параметрлерге сай жақын жерлерді ұсын.",
    "Жақын жерде не істеуге болады?",
])
def test_explicit_place_request_exits_event_context_and_discards_old_date(message):
    request = RecommendRequest(message=message, conversation={"interests": ["events"], "event_date": "2026-10-28"})
    resolved = resolve_constraints(request, None, set())
    assert "events" not in resolved["interests"] and resolved["event_date"] is None


@pytest.mark.parametrize("message,expected_date", [
    ("Tomorrow?", "2026-10-21"), ("А завтра?", "2026-10-21"), ("Ал ертең?", "2026-10-21"),
    ("2026-10-29", "2026-10-29"), ("What other events?", "2026-10-28"),
])
def test_short_calendar_followup_keeps_events_and_changes_date(message, expected_date):
    request = RecommendRequest(message=message, starts_at="2026-10-20T14:00:00+05:00",
                               conversation={"interests": ["events"], "event_date": "2026-10-28"})
    resolved = resolve_constraints(request, None, set())
    assert "events" in resolved["interests"] and resolved["event_date"] == expected_date


def test_weather_uses_same_environment_decision_and_retains_it_for_followup(tiny_agent, monkeypatch):
    async def check():
        request = RecommendRequest(message="Только в помещении, не на улице", indoor=False)
        first = tiny_agent.context({"request": request.model_dump(exclude_unset=True), "trace": []})
        response = await tiny_agent.external_context(first)
        assert response["context"]["indoor"] is True
        assert response["context"]["weather_effect"]["explicit_outdoor_request"] is False
        outdoors = RecommendRequest(message="На свежем воздухе", indoor=True)
        second = tiny_agent.context({"request": outdoors.model_dump(exclude_unset=True), "trace": []})
        result = await tiny_agent.external_context(second)
        assert result["context"]["indoor"] is False
        assert result["context"]["weather_effect"]["explicit_outdoor_request"] is True
        conversation = {key: value for key, value in result["context"]["conversation"].items() if key in ConversationContext.model_fields}
        followup = RecommendRequest(message="Поближе", conversation=conversation)
        next_state = tiny_agent.context({"request": followup.model_dump(exclude_unset=True), "trace": []})
        final = await tiny_agent.external_context(next_state)
        assert final["context"]["weather_effect"]["explicit_outdoor_request"] is True
    asyncio.run(check())


def test_overture_status_requires_published_release_metadata(tiny_agent):
    from backend.integrations import describe_integrations
    assert not any(item.id == "overture" for item in describe_integrations(tiny_agent).integrations)
    tiny_agent.dataset["metadata"]["additional_collections"] = [{"provider": "Overture Maps", "release": "2026-09-23.1"}]
    entry = next(item for item in describe_integrations(tiny_agent).integrations if item.id == "overture")
    assert entry.status == "active" and entry.configured and not entry.live_verified
    assert "2026-09-23.1" in entry.detail and "not a customer rating" in entry.detail


