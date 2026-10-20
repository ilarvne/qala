import pytest

from scripts.providers.google import parse_html, parse_visible_card
from scripts.crawl_google_public import ProviderAccessDenied, google_robots_allows, preflight, run_capture
from scripts.providers.common import correlate


URL = "https://www.google.com/maps/place/Bayterek/@50,70,15z/data=!1s0x4245841e0caadcf7:0x4f6ce0ff87111d39!8m2!3d51.128316!4d71.4305155?entry=ttu&g_ep=tracking"


@pytest.fixture(autouse=True)
def isolated_private_crawl_state(monkeypatch, tmp_path):
    import scripts.crawl_google_public as capture
    ticks = {"time": 1792512000.0}
    monkeypatch.setattr(capture, "DEFAULT_STATE_PATH", tmp_path / "private" / "control-state.json")
    monkeypatch.setattr(capture, "DEFAULT_CLOCK", lambda: ticks["time"])
    monkeypatch.setattr(capture, "DEFAULT_SLEEP", lambda seconds: ticks.__setitem__("time", ticks["time"] + seconds))


def test_primary_header_never_uses_nested_business_rating_or_count():
    row = parse_visible_card({"name": "Bäiterek", "header_text": "4.6\nTourist attraction", "body_text": "Baiterek Coffee\n3.8(12)\nCoffee shop", "limited_version": True}, URL)
    assert row["rating"] == 4.6
    assert row["rating_count"] is None
    assert row["review_count"] is None
    assert row["lat"] == 51.128316
    assert row["lon"] == 71.4305155
    assert "g_ep" not in row["source_url"]
    assert row["import_policy"] == "evaluation_only"


def test_missing_primary_rating_remains_unknown_despite_body_content():
    row = parse_visible_card({"name": "Bäiterek", "header_text": "Tourist attraction", "body_text": "Baiterek Coffee\n3.8(12)"}, URL)
    assert row["rating"] is None


def test_alternate_language_heading_does_not_hide_primary_rating():
    row = parse_visible_card({"name": "Музей Сакена Сейфуллина", "header_text": "Сәкен Сейфуллин мұражайы\n4,6\nМузей", "body_text": "Nearby cafe\n3.8(12)"}, URL)
    assert row["rating"] == 4.6 and row["rating_count"] is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, 5.1, -1])
def test_invalid_rating_is_not_published(value):
    row = parse_visible_card({"name": "Bäiterek", "rating": value}, URL)
    assert row["rating"] is None


def test_viewport_is_not_entity_coordinate():
    row = parse_visible_card({"name": "Cafela"}, "https://www.google.com/maps/search/?api=1&query=Cafela+Astana")
    assert row["lat"] is None
    assert row["lon"] is None
    assert row["provider_id"] is None


def test_non_google_source_rejected():
    with pytest.raises(ValueError):
        parse_visible_card({"name": "Bayterek"}, "https://google.com.evil.invalid/maps/place/Bayterek")


def test_bootstrap_internal_arrays_are_not_parsed():
    assert parse_html('<title>Google Maps</title><script>window.APP_INITIALIZATION_STATE=["Bayterek",4.6,9999]</script>', URL) == []


def test_explicit_jsonld_aggregate_fields_are_separate():
    html = '<script type="application/ld+json">{"@type":"Museum","name":"National Museum","aggregateRating":{"ratingValue":"4.8","ratingCount":"1 234","reviewCount":"78"}}</script>'
    row, = parse_html(html, URL)
    assert row["rating"] == 4.8
    assert row["rating_count"] == 1234
    assert row["review_count"] == 78
    assert row["access_method"] == "http"


def test_permanent_closure_is_recorded_as_source_discrepancy():
    row = parse_visible_card({"name": "Cafela", "header_text": "4.2\nМүлдем жабық"}, URL)
    assert any("permanently closed" in warning for warning in row["warnings"])


def test_google_robots_uses_longest_rule_and_default_deny():
    robots = "User-agent: *\nUser-agent: Yandex\nDisallow: /maps/\nAllow: /maps/search/\nAllow: /maps/place/\nDisallow: /maps/place/private/\nUser-agent: AdsBot-Google\nDisallow: /"
    assert google_robots_allows(robots, "https://www.google.com/maps/search/?api=1&query=Astana")
    assert google_robots_allows(robots, URL)
    assert not google_robots_allows(robots, "https://www.google.com/maps/place/private/card")
    assert not google_robots_allows(robots, "https://www.google.com/maps/private-api")
    assert not google_robots_allows("User-agent: *\nDisallow: /maps/", URL)
    assert not google_robots_allows("User-agent: *\nAllow: /", "https://google.evil.invalid/maps/place/Bayterek")


@pytest.mark.parametrize("status", [401, 403, 429])
def test_http_denial_prevents_browser_fallback(monkeypatch, tmp_path, status):
    from urllib.error import HTTPError
    import scripts.crawl_google_public as capture
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def read(self, *_):
            return b"User-agent: *\nAllow: /maps/search/\nAllow: /maps/place/\n"
    def open_url(request, **_):
        if request.full_url.endswith("robots.txt"):
            return Response()
        raise HTTPError(request.full_url, status, "Denied", None, None)
    monkeypatch.setattr(capture, "urlopen", open_url)
    def forbidden_browser(*_, **__):
        pytest.fail("A denied HTTP request must never fall back to the browser")
    monkeypatch.setattr(capture.subprocess, "run", forbidden_browser)
    result = run_capture("not-called", tmp_path)
    assert len(result["probes"]) == 1
    assert result["probes"][0]["status"] == "provider_stopped"
    assert result["rows"] == []


def test_browser_challenge_stops_remaining_seeds(monkeypatch, tmp_path):
    from types import SimpleNamespace
    import scripts.crawl_google_public as capture
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def read(self, *_):
            return b"User-agent: *\nAllow: /maps/search/\nAllow: /maps/place/\n"
    monkeypatch.setattr(capture, "urlopen", lambda *_, **__: Response())
    preflights = []
    monkeypatch.setattr(capture, "preflight", lambda url: preflights.append(url) or {"http_status": 200})
    commands = []
    def browser(command, **_):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout='{"access_denied":true}' if "eval" in command else "Done")
    monkeypatch.setattr(capture.subprocess, "run", browser)
    result = run_capture("browser", tmp_path)
    assert len(preflights) == 1
    assert sum("open" in command for command in commands) == 1
    assert len(result["probes"]) == 1
    assert result["probes"][0]["status"] == "provider_stopped"


def test_nearby_wrong_business_does_not_match_requested_seed():
    row = parse_visible_card({"name": "Wrong nearby cafe", "header_text": "4.9"}, URL, observed_at="2026-10-20T12:00:00+00:00")
    row["matched_poi_ids"] = ["requested-seed-cafela"]
    local = [{"id": "requested-seed-cafela", "name": "Cafela", "names": {}, "lat": 51.12832, "lon": 71.43051}]
    result = correlate(row, local)
    assert result["matched_poi_ids"] == []
    assert any("No exact local name" in warning for warning in result["warnings"])


def test_cached_html_reparse_preserves_original_acquisition_time():
    html = '<script type="application/ld+json">{"@type":"Museum","name":"National Museum"}</script>'
    acquired = "2024-01-02T03:04:05+06:00"
    original = parse_html(html, URL, observed_at=acquired)[0]
    replay = parse_html(html, URL, observed_at=acquired)[0]
    assert original["observed_at"] == replay["observed_at"] == acquired
    assert not any("acquisition time is unknown" in warning for warning in replay["warnings"])


def test_cached_html_without_acquisition_metadata_remains_unknown():
    html = '<script type="application/ld+json">{"@type":"Museum","name":"National Museum"}</script>'
    row = parse_html(html, URL)[0]
    assert row["observed_at"] is None
    assert any("Original acquisition time is unknown" in warning for warning in row["warnings"])


def test_visible_card_preserves_capture_acquisition_time():
    acquired = "2024-01-02T03:04:05+06:00"
    card = {"name": "Bayterek", "header_text": "4.6", "observed_at": acquired}
    assert parse_visible_card(card, URL)["observed_at"] == acquired
    assert parse_visible_card(card, URL)["observed_at"] == acquired


def test_visible_card_without_capture_acquisition_time_remains_unknown():
    row = parse_visible_card({"name": "Bayterek", "header_text": "4.6"}, URL)
    assert row["observed_at"] is None
    assert any("Original acquisition time is unknown" in warning for warning in row["warnings"])


@pytest.mark.parametrize("status", [401, 403, 429])
def test_browser_document_denial_stops_without_a_body_challenge(monkeypatch, tmp_path, status):
    from types import SimpleNamespace
    import json
    import scripts.crawl_google_public as capture
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def read(self, *_):
            return b"User-agent: *\nAllow: /maps/search/\nAllow: /maps/place/\n"
    monkeypatch.setattr(capture, "urlopen", lambda *_, **__: Response())
    preflights = []
    monkeypatch.setattr(capture, "preflight", lambda url: preflights.append(url) or {"http_status": 200})
    card = {"name": "Bayterek", "url": URL, "header_text": "4.6", "document_status": status, "access_denied": False}
    commands = []
    def browser(command, **_):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps(card) if "eval" in command else "Done")
    monkeypatch.setattr(capture.subprocess, "run", browser)
    result = run_capture("browser", tmp_path)
    assert len(preflights) == 1
    assert sum("open" in command for command in commands) == 1
    assert result["rows"] == []
    assert result["probes"][0]["preflight_http_status"] == 200
    assert result["probes"][0]["browser_document_http_status"] == status
    assert result["probes"][0]["status"] == "provider_stopped"


def test_unknown_browser_status_never_inherits_preflight_200(monkeypatch, tmp_path):
    from types import SimpleNamespace
    import json
    import scripts.crawl_google_public as capture
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def read(self, *_):
            return b"User-agent: *\nAllow: /maps/search/\nAllow: /maps/place/\n"
    monkeypatch.setattr(capture, "urlopen", lambda *_, **__: Response())
    monkeypatch.setattr(capture, "preflight", lambda _: {"http_status": 200})
    card = {"name": "Bayterek", "url": URL, "header_text": "4.6", "document_status": 0}
    monkeypatch.setattr(capture.subprocess, "run", lambda command, **_: SimpleNamespace(returncode=0, stdout=json.dumps(card) if "eval" in command else "Done"))
    result = run_capture("browser", tmp_path, limit=1)
    assert result["probes"][0]["preflight_http_status"] == 200
    assert result["probes"][0]["browser_document_http_status"] is None
    assert result["rows"][0]["http_status"] is None


LOCAL = [
    {"id": "osm-way-230401645", "name": "Bayterek", "names": {}, "lat": 51.128316, "lon": 71.4305155},
    {"id": "osm-node-5936638686", "name": "Cafela", "names": {}, "lat": 51.1354693, "lon": 71.4306146},
]
CURATED = [{"poi_id": item["id"], "query": item["name"] + " Astana", "slug": item["name"].lower()} for item in LOCAL]


def _mock_public_capture(monkeypatch, clock=None):
    import json
    from types import SimpleNamespace
    import scripts.crawl_google_public as capture
    events, current = [], {"poi": LOCAL[0]}
    now = clock or capture.DEFAULT_CLOCK
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def read(self, *_):
            return b"User-agent: *\nAllow: /maps/search/\nAllow: /maps/place/\n"
    def robots(*_, **__):
        events.append(("robots", now()))
        return Response()
    def preflight(url):
        events.append(("preflight", now()))
        current["poi"] = LOCAL[1] if "Cafela" in url else LOCAL[0]
        return {"http_status": 200}
    def browser(command, **_):
        if "open" in command:
            events.append(("browser", now()))
        poi = current["poi"]
        url = URL if poi is LOCAL[0] else "https://www.google.com/maps/place/Cafela/data=!1s0x424586a6840d88e1:0x26b2e7adc4995c33!8m2!3d51.1354693!4d71.4306146"
        card = {"url": url, "name": poi["name"], "header_text": "4.6", "document_status": 200}
        return SimpleNamespace(returncode=0, stdout=json.dumps(card) if "eval" in command else "Done")
    monkeypatch.setattr(capture, "urlopen", robots)
    monkeypatch.setattr(capture, "preflight", preflight)
    monkeypatch.setattr(capture.subprocess, "run", browser)
    return events


def test_persisted_denial_stops_next_invocation_before_any_transport(monkeypatch, tmp_path):
    import scripts.crawl_google_public as capture
    _mock_public_capture(monkeypatch)
    monkeypatch.setattr(capture, "preflight", lambda _: (_ for _ in ()).throw(ProviderAccessDenied("HTTP403", http_status=403)))
    first = run_capture("browser", tmp_path / "evidence", seeds=CURATED[:1], catalogue=LOCAL)
    assert first["status"] == "provider_stopped"
    def forbidden(*_, **__):
        pytest.fail("Persistent denial must be checked before any HTTP or browser access")
    monkeypatch.setattr(capture, "urlopen", forbidden)
    monkeypatch.setattr(capture, "preflight", forbidden)
    monkeypatch.setattr(capture.subprocess, "run", forbidden)
    second = run_capture("browser", tmp_path / "evidence", seeds=CURATED[:1], catalogue=LOCAL, language="en", refresh_after_hours=1)
    assert second["status"] == "provider_stopped" and second["new_attempts"] == 0
    assert second["probes"] == first["probes"]
    assert second["stop"]["http_status"] == 403


def test_resume_skips_success_across_languages_and_preserves_original_rows(monkeypatch, tmp_path):
    import scripts.crawl_google_public as capture
    _mock_public_capture(monkeypatch)
    first = run_capture("browser", tmp_path / "evidence", seeds=CURATED[:1], catalogue=LOCAL)
    original = first["rows"][0].copy()
    def forbidden(*_, **__):
        pytest.fail("Already acquired seed must not be fetched again just to change UI language")
    monkeypatch.setattr(capture, "urlopen", forbidden)
    monkeypatch.setattr(capture, "preflight", forbidden)
    monkeypatch.setattr(capture.subprocess, "run", forbidden)
    second = run_capture("browser", tmp_path / "evidence", seeds=CURATED[:1], catalogue=LOCAL, language="kk")
    assert second["status"] == "cached" and second["new_attempts"] == 0
    assert second["rows"] == [original]
    assert second["skipped_seed_ids"] == [LOCAL[0]["id"]]


def test_prior_output_bootstraps_resume_without_redating_or_network(monkeypatch, tmp_path):
    import json
    import scripts.crawl_google_public as capture
    acquired = "2020-01-02T03:04:05+06:00"
    row = parse_visible_card({"name": "Bayterek", "observed_at": acquired}, URL)
    output = tmp_path / "evidence"
    output.mkdir()
    (output / "rows.json").write_text(json.dumps([row]))
    probe = {"requested_poi_id": LOCAL[0]["id"], "provider_id": row["provider_id"], "observed_at": acquired, "status": "visible_card_observed"}
    (output / "browser-probes.json").write_text(json.dumps([probe]))
    monkeypatch.setattr(capture, "urlopen", lambda *_, **__: pytest.fail("Historic successful acquisition must be resumed without another request"))
    result = run_capture("browser", output, seeds=CURATED[:1], catalogue=LOCAL)
    assert result["status"] == "cached"
    assert result["rows"][0]["observed_at"] == acquired
    assert result["probes"] == [probe]


def test_all_explicit_request_starts_are_paced_with_injected_clock(monkeypatch, tmp_path):
    current, sleeps = [1000.0], []
    def clock():
        return current[0]
    def sleep(seconds):
        sleeps.append(seconds)
        current[0] += seconds
    events = _mock_public_capture(monkeypatch, clock)
    result = run_capture("browser", tmp_path / "evidence", seeds=CURATED, catalogue=LOCAL, clock=clock, sleep=sleep)
    assert result["new_attempts"] == 2 and result["new_successes"] == 2
    assert [kind for kind, _ in events] == ["robots", "preflight", "browser", "preflight", "browser"]
    starts = [stamp for _, stamp in events]
    assert all(second - first >= 3 for first, second in zip(starts, starts[1:]))
    assert sleeps == [3, 3, 3, 3]


@pytest.mark.parametrize("invalid", [
    [], [{"poi_id": "missing", "query": "Missing museum Astana"}],
    [{"poi_id": LOCAL[0]["id"], "query": " "}],
    [{"poi_id": LOCAL[0]["id"], "query": "https://maps.google.com"}],
    [{"poi_id": LOCAL[0]["id"], "query": "Bayterek Astana", "slug": "../escape"}],
    CURATED[:1] * 2, CURATED[:1] * 7,
])
def test_invalid_or_bulk_seeds_fail_before_network(monkeypatch, tmp_path, invalid):
    import scripts.crawl_google_public as capture
    monkeypatch.setattr(capture, "urlopen", lambda *_, **__: pytest.fail("Invalid curated seeds cannot start acquisition"))
    with pytest.raises(ValueError):
        run_capture("browser", tmp_path / "evidence", seeds=invalid, catalogue=LOCAL)


def test_anonymous_derived_place_cannot_be_a_named_curated_seed():
    from scripts.crawl_google_public import validate_seeds
    with pytest.raises(ValueError, match="explicitly named"):
        validate_seeds(CURATED[:1], [{**LOCAL[0], "name_derived": True}])


def test_failed_acquisition_remains_retryable_and_does_not_erase_prior_probe(monkeypatch, tmp_path):
    import scripts.crawl_google_public as capture
    from scripts.providers.crawl_state import CrawlState
    _mock_public_capture(monkeypatch)
    monkeypatch.setattr(capture, "preflight", lambda _: (_ for _ in ()).throw(TimeoutError("Temporary failure")))
    output = tmp_path / "evidence"
    first = run_capture("browser", output, seeds=CURATED[:1], catalogue=LOCAL)
    assert first["status"] == "partial" and first["new_failures"] == 1
    with CrawlState(capture.DEFAULT_STATE_PATH) as state:
        assert not state.should_skip("google", LOCAL[0]["id"], capture.DEFAULT_CLOCK())
    _mock_public_capture(monkeypatch)
    second = run_capture("browser", output, seeds=CURATED[:1], catalogue=LOCAL)
    assert second["new_successes"] == 1
    assert len(second["probes"]) == 2
    assert second["probes"][0] == first["probes"][0]


def test_output_replace_failure_preserves_prior_json_and_ledger_restores_capture(monkeypatch, tmp_path):
    import scripts.crawl_google_public as capture
    output = tmp_path / "evidence"
    output.mkdir()
    (output / "rows.json").write_text("[]\n")
    original_bytes = (output / "rows.json").read_bytes()
    _mock_public_capture(monkeypatch)
    atomic_write = capture.atomic_json_write
    def fail_rows(path, value):
        if path.name == "rows.json":
            raise OSError("Injected output replacement failure")
        atomic_write(path, value)
    monkeypatch.setattr(capture, "atomic_json_write", fail_rows)
    with pytest.raises(OSError, match="replacement failure"):
        run_capture("browser", output, seeds=CURATED[:1], catalogue=LOCAL)
    assert (output / "rows.json").read_bytes() == original_bytes
    monkeypatch.setattr(capture, "atomic_json_write", atomic_write)
    monkeypatch.setattr(capture, "urlopen", lambda *_, **__: pytest.fail("Captured row survives privately; no new request needed after output failure"))
    result = run_capture("browser", output, seeds=CURATED[:1], catalogue=LOCAL)
    assert result["status"] == "cached" and len(result["rows"]) == 1
    assert result["rows"][0]["observed_at"] is not None


def _override_browser_card(monkeypatch, card, *, wait_timeout=False, inspection_failure=None):
    import json
    from types import SimpleNamespace
    import subprocess
    import scripts.crawl_google_public as capture
    previous, commands = capture.subprocess.run, []
    def browser(command, **kwargs):
        commands.append(command)
        if "wait" in command and wait_timeout:
            raise subprocess.TimeoutExpired(command, 28)
        if "eval" in command:
            if inspection_failure == "timeout":
                raise subprocess.TimeoutExpired(command, 15)
            return SimpleNamespace(returncode=0, stdout="invalid JSON" if inspection_failure == "json" else json.dumps(card))
        return previous(command, **kwargs)
    monkeypatch.setattr(capture.subprocess, "run", browser)
    return commands


@pytest.mark.parametrize("distance", [150.0, 200.04, None])
def test_unmatched_acquisition_requires_nearby_entity_coordinates(monkeypatch, tmp_path, distance):
    import math
    import scripts.crawl_google_public as capture
    from scripts.providers.crawl_state import CrawlState
    _mock_public_capture(monkeypatch)
    lat = LOCAL[0]["lat"] + math.degrees(distance / 6371000) if distance is not None else None
    url = ("https://www.google.com/maps/place/Unresolved/data=!1s0x4245841e0caadcf7:0x4f6ce0ff87111d39"
           + (f"!8m2!3d{lat}!4d{LOCAL[0]['lon']}" if lat is not None else ""))
    card = {"url": url, "name": "Unresolved transliteration", "header_text": "4.6", "document_status": 200}
    _override_browser_card(monkeypatch, card)
    result = run_capture("browser", tmp_path / "evidence", seeds=CURATED[:1], catalogue=LOCAL)
    assert len(result["rows"]) == 1  # Authentic raw observations remain inspectable.
    assert result["rows"][0]["matched_poi_ids"] == []
    assert result["probes"][0]["identity_requires_review"]
    eligible = distance is not None and distance <= 200
    assert result["new_successes"] == int(eligible)
    with CrawlState(capture.DEFAULT_STATE_PATH) as state:
        assert state.should_skip("google", LOCAL[0]["id"], capture.DEFAULT_CLOCK()) is eligible
    if distance == 200.04:
        assert result["probes"][0]["distance_from_seed_m"] == 200.0
        assert result["probes"][0]["status"] == "entity_outside_seed_bounds"


@pytest.mark.parametrize("origin", ["output", "ledger"])
@pytest.mark.parametrize("missing_coordinates", [False, True])
def test_bad_historical_success_never_suppresses_the_requested_seed(monkeypatch, tmp_path, origin, missing_coordinates):
    import json
    import scripts.crawl_google_public as capture
    from scripts.providers.crawl_state import CrawlState
    acquired = "2020-01-02T03:04:05+06:00"
    bad_url = ("https://www.google.com/maps/place/Unresolved/data=!1s0x4245841e0caadcf7:0x4f6ce0ff87111d39"
               + ("" if missing_coordinates else "!8m2!3d50.0!4d70.0"))
    row = parse_visible_card({"name": "Unresolved", "observed_at": acquired}, bad_url)
    output = tmp_path / "evidence"
    if origin == "output":
        output.mkdir()
        (output / "rows.json").write_text(json.dumps([row]))
        probe = {"requested_poi_id": LOCAL[0]["id"], "provider_id": row["provider_id"], "observed_at": acquired, "status": "visible_card_observed"}
        (output / "browser-probes.json").write_text(json.dumps([probe]))
    else:
        with CrawlState(capture.DEFAULT_STATE_PATH) as state:
            state.record_success("google", LOCAL[0]["id"], acquired, row)
    events = _mock_public_capture(monkeypatch)
    result = run_capture("browser", output, seeds=CURATED[:1], catalogue=LOCAL)
    assert result["new_attempts"] == result["new_successes"] == 1
    assert events and result["skipped_seed_ids"] == []
    if origin == "output":
        assert result["rows"][0] == row
    else:
        assert row not in result["rows"]
        with CrawlState(capture.DEFAULT_STATE_PATH) as state:
            assert state.provider("google")["seeds"][LOCAL[0]["id"]]["successes"][0]["row"] == row


def test_recent_distant_cache_does_not_extend_freshness_of_old_nearby_observation(monkeypatch, tmp_path):
    import scripts.crawl_google_public as capture
    from scripts.providers.crawl_state import CrawlState
    old = "2020-01-02T03:04:05+06:00"
    recent = "2026-10-20T16:00:00+00:00"
    near = parse_visible_card({"name": "Bayterek", "observed_at": old}, URL)
    far_url = "https://www.google.com/maps/place/Unresolved/data=!1s0x4245841e0caadcf7:0x4f6ce0ff87111d39!8m2!3d50.0!4d70.0"
    far = parse_visible_card({"name": "Unresolved", "observed_at": recent}, far_url)
    with CrawlState(capture.DEFAULT_STATE_PATH) as state:
        state.record_success("google", LOCAL[0]["id"], old, near)
        state.record_success("google", LOCAL[0]["id"], recent, far)
    _mock_public_capture(monkeypatch)
    result = run_capture("browser", tmp_path / "evidence", seeds=CURATED[:1], catalogue=LOCAL, refresh_after_hours=24)
    assert result["new_attempts"] == result["new_successes"] == 1
    assert near in result["rows"] and far not in result["rows"]


def test_wait_timeout_still_inspects_browser429_and_stops_remaining_seeds(monkeypatch, tmp_path):
    import scripts.crawl_google_public as capture
    _mock_public_capture(monkeypatch)
    card = {"url": URL, "name": "Bayterek", "header_text": "4.6", "document_status": 429, "access_denied": False}
    commands = _override_browser_card(monkeypatch, card, wait_timeout=True)
    result = run_capture("browser", tmp_path / "evidence", seeds=CURATED, catalogue=LOCAL)
    assert any("eval" in command for command in commands)
    assert sum("open" in command for command in commands) == 1
    assert result["status"] == "provider_stopped" and result["new_attempts"] == 1
    assert result["probes"][0]["readiness_wait_timed_out"]
    assert result["probes"][0]["browser_document_http_status"] == 429
    assert result["rows"] == []


@pytest.mark.parametrize("inspection_failure", ["timeout", "json", "unknown_status"])
def test_wait_timeout_with_unavailable_inspection_defers_provider_persistently(monkeypatch, tmp_path, inspection_failure):
    import scripts.crawl_google_public as capture
    _mock_public_capture(monkeypatch)
    card = {"url": URL, "name": "Bayterek", "header_text": "4.6", "document_status": None}
    _override_browser_card(monkeypatch, card, wait_timeout=True, inspection_failure=inspection_failure)
    output = tmp_path / "evidence"
    first = run_capture("browser", output, seeds=CURATED, catalogue=LOCAL)
    assert first["status"] == "provider_stopped" and first["new_attempts"] == 1
    def forbidden(*_, **__):
        pytest.fail("Unknown access state after timeout cannot trigger a new transport request")
    monkeypatch.setattr(capture, "urlopen", forbidden)
    monkeypatch.setattr(capture.subprocess, "run", forbidden)
    second = run_capture("browser", output, seeds=CURATED, catalogue=LOCAL)
    assert second["status"] == "provider_stopped" and second["new_attempts"] == 0
    assert second["stop"]["http_status"] is None
    assert "defer provider" in second["stop"]["reason"]


def test_wait_timeout_with_verified200_and_valid_entity_can_finish(monkeypatch, tmp_path):
    _mock_public_capture(monkeypatch)
    card = {"url": URL, "name": "Bayterek", "header_text": "4.6", "document_status": 200}
    _override_browser_card(monkeypatch, card, wait_timeout=True)
    result = run_capture("browser", tmp_path / "evidence", seeds=CURATED[:1], catalogue=LOCAL)
    assert result["new_successes"] == 1
    assert result["probes"][0]["readiness_wait_timed_out"]
