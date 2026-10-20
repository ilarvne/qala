import os
import stat
import subprocess
import sys
from datetime import datetime

import pytest

from scripts.providers.crawl_state import (
    DEFAULT_STATE_PATH,
    CrawlState,
    CrawlStateCorrupt,
    CrawlStateError,
    CrawlStateLocked,
    ProviderStopped,
    atomic_json_write,
    canonical_provider,
)


ACQUIRED = "2026-10-20T12:30:00+06:00"


def test_default_is_absolute_private_project_path():
    assert DEFAULT_STATE_PATH.is_absolute()
    assert DEFAULT_STATE_PATH.parts[-3:] == (".local", "provider-crawl", "control-state.json")


@pytest.mark.parametrize("alias", ["google", "www.google.com", "maps.google.com", "https://google.kz/maps/place/Example", "https://consent.google.com/m"])
def test_public_google_aliases_share_one_provider(alias):
    assert canonical_provider(alias) == "google"


@pytest.mark.parametrize("alias", ["2gis.kz", "www.2gis.kz", "captcha.2gis.ru", "www2gis"])
def test_2gis_captcha_and_public_hosts_share_state(alias):
    assert canonical_provider(alias) == "2gis"


@pytest.mark.parametrize("alias", ["yandex.ru", "yandex.kz", "yandex.com", "https://smartcaptcha.yandexcloud.net/captcha"])
def test_yandex_captcha_and_public_hosts_share_state(alias):
    assert canonical_provider(alias) == "yandex"


def test_api_403_cannot_globally_stop_public_maps(tmp_path):
    path = tmp_path / "private" / "state.json"
    with CrawlState(path) as state:
        state.stop("https://places.googleapis.com/v1/places", "missing_api_key", ACQUIRED, 403)
        assert state.is_stopped("google_places_api")
        assert not state.is_stopped("google.com")
        state.record_attempt("maps.google.com", "seed", ACQUIRED)
    with CrawlState(path) as state:
        assert state.is_stopped("places.googleapis.com")
        assert not state.is_stopped("google")
    assert canonical_provider("catalog.api.2gis.com") != "2gis"
    assert canonical_provider("geocode-maps.yandex.ru") != "yandex"


def test_provider_denial_survives_reopen_before_any_work(tmp_path):
    path = tmp_path / "state.json"
    with CrawlState(path) as state:
        first = state.stop("google.kz", "captcha", ACQUIRED, 429, "https://google.kz/sorry")
    with CrawlState(path) as state:
        assert state.is_stopped("maps.google.com")
        assert state.should_skip("google", "never-attempted", 0)
        with pytest.raises(ProviderStopped):
            state.begin_attempt("www.google.com", "seed", clock=lambda: 0, sleep=lambda _: pytest.fail("Stopped providers must not sleep or start work"))
        with pytest.raises(ProviderStopped):
            state.record_attempt("google", "seed", ACQUIRED)
        assert state.stop("google", "different-reason", "2026-10-21T00:00:00Z", 403) == first
        assert not state.provider("google")["seeds"]


def test_nonblocking_lock_prevents_another_process_and_releases(tmp_path):
    path = tmp_path / "state.json"
    script = "from scripts.providers.crawl_state import CrawlState, CrawlStateLocked; import sys\ntry:\n with CrawlState(sys.argv[1]): pass\nexcept CrawlStateLocked:\n sys.exit(73)\n"
    with CrawlState(path):
        result = subprocess.run([sys.executable, "-c", script, str(path)], capture_output=True, text=True, timeout=5)
        assert result.returncode == 73, result.stderr
        with pytest.raises(CrawlStateLocked):
            with CrawlState(path):
                pass
    with CrawlState(path) as state:
        assert state.data == {"version": 1, "providers": {}}


@pytest.mark.parametrize("content", ["", "{", "null", '{"version":1,"providers":[],"stopped":false}', '{"version":1,"providers":{},"providers":{}}', '{"version":1,"providers":{"google":{"stopped":false,"stop":null,"last_started_at":NaN,"seeds":{}}}}'])
def test_corruption_fails_closed_without_reset_or_lock_leak(tmp_path, content):
    path = tmp_path / "state.json"
    path.write_text(content)
    for _ in range(2):
        with pytest.raises(CrawlStateCorrupt):
            with CrawlState(path):
                pytest.fail("Malformed ledgers cannot begin work")
        assert path.read_text() == content


def test_original_rows_and_timezone_timestamps_survive_refresh(tmp_path):
    path = tmp_path / "state.json"
    row = {"name": "Original", "observed_at": ACQUIRED, "rating": None}
    later = "2026-10-22T06:30:00Z"
    with CrawlState(path) as state:
        state.record_attempt("google", "seed", ACQUIRED)
        state.record_success("google", "seed", ACQUIRED, row)
        row["name"] = "Caller mutation"
        state.record_attempt("google.com", "seed", later)
        state.record_success("maps.google.com", "seed", later, {"name": "Refresh", "observed_at": later, "rating": 4.5})
        snapshot = state.provider("google")
        snapshot["seeds"].clear()
    with CrawlState(path) as state:
        seed = state.provider("google")["seeds"]["seed"]
        assert seed["attempts"] == [{"started_at": ACQUIRED}, {"started_at": later}]
        assert [result["observed_at"] for result in seed["successes"]] == [ACQUIRED, later]
        assert seed["successes"][0]["row"] == {"name": "Original", "observed_at": ACQUIRED, "rating": None}
        assert seed["successes"][1]["row"]["name"] == "Refresh"
        assert state.should_skip("google", "seed", "2050-01-01T00:00:00Z")
        assert state.should_skip("google", "seed", "2026-10-22T07:00:00Z", refresh_after_hours=1)
        assert not state.should_skip("google", "seed", "2026-10-22T07:30:00Z", refresh_after_hours=1)


def test_success_bootstrap_is_idempotent_and_never_replaces_original(tmp_path):
    path = tmp_path / "state.json"
    with CrawlState(path) as state:
        state.record_success("google", "seed", ACQUIRED, {"name": "Original", "evidence_sha256": "capture-1"})
        original = path.read_bytes()
        state.record_success("maps.google.com", "seed", ACQUIRED, {"name": "Reparsed", "evidence_sha256": "capture-1"})
        assert path.read_bytes() == original
        state.record_success("google", "seed", ACQUIRED, {"name": "Distinct evidence", "evidence_sha256": "capture-2"})
        state.record_success("google", "seed", "2026-10-21T00:00:00Z", {"name": "New acquisition", "evidence_sha256": "capture-1"})
        successes = state.provider("google")["seeds"]["seed"]["successes"]
        assert len(successes) == 3
        assert successes[0]["row"]["name"] == "Original"


def test_rows_without_evidence_hash_only_dedupe_exact_original_capture(tmp_path):
    with CrawlState(tmp_path / "state.json") as state:
        state.record_success("2gis", "seed", None, {"name": "Original"})
        state.record_success("2gis", "seed", None, {"name": "Original"})
        state.record_success("2gis", "seed", None, {"name": "Distinct"})
        assert len(state.provider("2gis")["seeds"]["seed"]["successes"]) == 2


def test_failed_attempt_is_not_fresh_success_and_unknown_time_is_not_refreshed(tmp_path):
    with CrawlState(tmp_path / "state.json") as state:
        state.record_attempt("2gis", "failed", ACQUIRED)
        assert not state.should_skip("2gis", "failed", ACQUIRED)
        assert not state.should_skip("2gis", "failed", ACQUIRED, refresh_after_hours=24)
        state.record_success("2gis", "unknown-time", None, {"name": "Cached", "observed_at": None})
        assert state.should_skip("2gis", "unknown-time", ACQUIRED)
        assert not state.should_skip("2gis", "unknown-time", ACQUIRED, refresh_after_hours=24)


def test_pacing_uses_shared_alias_last_start_and_records_actual_start_only(tmp_path):
    path = tmp_path / "state.json"
    current = [100.0]
    sleeps = []
    def clock():
        return current[0]
    def sleep(seconds):
        sleeps.append(seconds)
        current[0] += seconds
    with CrawlState(path) as state:
        first = state.begin_attempt("yandex.ru", "first", min_delay=0, clock=clock, sleep=sleep)
        assert first == "1970-01-01T00:01:40+00:00"
        current[0] = 101
        assert state.pace("smartcaptcha.yandexcloud.net", min_delay=0, clock=clock, sleep=sleep) == 2
        assert set(state.provider("yandex")["seeds"]) == {"first"}
        assert state.provider("yandex")["last_started_at"] == 100
        second = state.begin_attempt("yandex.kz", "second", min_delay=0, clock=clock, sleep=sleep)
        assert second == "1970-01-01T00:01:43+00:00"
        assert sleeps == [2]
    current[0] = 104
    with CrawlState(path) as state:
        third = state.begin_attempt("yandex.com", "third", min_delay=5, clock=clock, sleep=sleep)
        assert datetime.fromisoformat(third).timestamp() == 108
        assert sleeps == [2, 4]


def test_pacing_failure_does_not_record_unstarted_attempt(tmp_path):
    with CrawlState(tmp_path / "state.json") as state:
        state.begin_attempt("google", "first", clock=lambda: 100, sleep=lambda _: None)
        with pytest.raises(CrawlStateError, match="Clock did not advance"):
            state.begin_attempt("google", "not-started", clock=lambda: 101, sleep=lambda _: None)
        assert set(state.provider("google")["seeds"]) == {"first"}


def test_private_directories_and_atomic_ledger_permissions(tmp_path):
    existing = tmp_path / "existing"
    existing.mkdir(mode=0o755)
    os.chmod(existing, 0o755)
    path = existing / "new" / "nested" / "state.json"
    with CrawlState(path) as state:
        state.record_attempt("2gis", "seed", ACQUIRED)
        lock_path = state.lock_path
    assert stat.S_IMODE(existing.stat().st_mode) == 0o755
    for directory in (path.parent, path.parent.parent):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(lock_path.stat().st_mode) == 0o600


def test_atomic_replace_error_preserves_old_file_and_removes_temporary(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    atomic_json_write(path, {"original": "kept"})
    original = path.read_bytes()
    import scripts.providers.crawl_state as control
    def fail_replace(*_):
        raise OSError("injected replacement failure")
    monkeypatch.setattr(control.os, "replace", fail_replace)
    with pytest.raises(OSError, match="injected"):
        atomic_json_write(path, {"new": "not committed"})
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_failed_commit_cannot_mutate_in_memory_state(tmp_path, monkeypatch):
    import scripts.providers.crawl_state as control
    path = tmp_path / "state.json"
    with CrawlState(path) as state:
        state.record_success("google", "seed", ACQUIRED, {"name": "Original"})
        original = path.read_bytes()
        def fail_write(*_):
            raise OSError("injected write failure")
        monkeypatch.setattr(control, "atomic_json_write", fail_write)
        with pytest.raises(OSError):
            state.stop("google", "denial", ACQUIRED, 403)
        assert not state.is_stopped("google")
        assert path.read_bytes() == original


def test_invalid_success_cannot_replace_existing_history(tmp_path):
    path = tmp_path / "state.json"
    with CrawlState(path) as state:
        state.record_success("google", "seed", ACQUIRED, {"rating": 4})
        original = path.read_bytes()
        with pytest.raises(ValueError):
            state.record_success("google", "seed", ACQUIRED, {"rating": float("nan")})
        assert path.read_bytes() == original
        assert len(state.provider("google")["seeds"]["seed"]["successes"]) == 1


def test_state_requires_lock_owning_context(tmp_path):
    state = CrawlState(tmp_path / "state.json")
    with pytest.raises(CrawlStateError):
        state.provider("google")
    assert not state.path.exists()
