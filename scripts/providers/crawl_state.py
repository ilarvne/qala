"""Private, process-safe control state for bounded provider audits.

Hold ``CrawlState`` as a context manager for the entire live run. A denial is
sticky across runs and public provider host aliases; there is deliberately no
reset method. Observation rows stay in this private ledger, never a public POI
export. Call ``begin_attempt`` immediately before each request, then record a
success only after acquisition and parsing have actually succeeded.
"""

from __future__ import annotations

import copy
import fcntl
import json
import math
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit


DEFAULT_STATE_PATH = Path(__file__).resolve().parents[2] / ".local/provider-crawl/control-state.json"


class CrawlStateError(RuntimeError):
    """The crawl cannot safely continue with its current control state."""


class CrawlStateLocked(CrawlStateError):
    """Another process already owns this crawl ledger."""


class CrawlStateCorrupt(CrawlStateError):
    """Existing state is invalid and requires explicit operator inspection."""


class ProviderStopped(CrawlStateError):
    """A persistent provider denial prevents further acquisition."""


_PUBLIC_ALIASES = {
    "google": "google", "google_maps": "google", "google_public": "google",
    "google.com": "google", "www.google.com": "google", "maps.google.com": "google",
    "google.kz": "google", "www.google.kz": "google", "maps.google.kz": "google",
    "google.ru": "google", "www.google.ru": "google", "maps.google.ru": "google",
    "consent.google.com": "google", "ipv4.google.com": "google",
    "2gis": "2gis", "2gis_public": "2gis", "www2gis": "2gis",
    "2gis.kz": "2gis", "www.2gis.kz": "2gis",
    "2gis.ru": "2gis", "www.2gis.ru": "2gis", "captcha.2gis.ru": "2gis",
    "yandex": "yandex", "yandex_maps": "yandex", "yandex_public": "yandex",
    "yandex.ru": "yandex", "www.yandex.ru": "yandex", "maps.yandex.ru": "yandex",
    "yandex.kz": "yandex", "www.yandex.kz": "yandex", "maps.yandex.kz": "yandex",
    "yandex.com": "yandex", "www.yandex.com": "yandex", "maps.yandex.com": "yandex",
    "smartcaptcha.yandexcloud.net": "yandex",
}
_API_ALIASES = {
    "places.googleapis.com": "google_places_api",
    "maps.googleapis.com": "google_maps_api",
    "catalog.api.2gis.com": "2gis_catalog_api",
    "routing.api.2gis.com": "2gis_routing_api",
    "tiles.api.2gis.com": "2gis_tiles_api",
    "geocode-maps.yandex.ru": "yandex_geocoder_api",
    "search-maps.yandex.ru": "yandex_search_api",
    "suggest-maps.yandex.ru": "yandex_suggest_api",
    "api-maps.yandex.ru": "yandex_maps_api",
}


def canonical_provider(value: str) -> str:
    """Normalize public hosts, without conflating their authenticated APIs."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A provider name or known provider hostname is required")
    name = value.strip().lower().rstrip(".")
    if name in _PUBLIC_ALIASES:
        return _PUBLIC_ALIASES[name]
    if name in _API_ALIASES:
        return _API_ALIASES[name]
    if re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", name):
        return name
    try:
        parsed = urlsplit(name if "://" in name else "//" + name)
        host = (parsed.hostname or "").rstrip(".")
    except ValueError as exc:
        raise ValueError("Invalid provider hostname") from exc
    if host in _API_ALIASES:
        return _API_ALIASES[host]
    if host in _PUBLIC_ALIASES:
        return _PUBLIC_ALIASES[host]
    raise ValueError("Unrecognized provider hostname")


def _mkdir_private(path: Path) -> None:
    """Create missing directories with 0700, preserving existing permissions."""
    missing: list[Path] = []
    parent = path
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    if not parent.is_dir():
        raise NotADirectoryError(parent)
    for directory in reversed(missing):
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            if not directory.is_dir():
                raise


def atomic_json_write(path: str | Path, data: Any) -> None:
    """Replace JSON durably with mode 0600; failures never leave partial JSON."""
    destination = Path(path).expanduser().absolute()
    payload = (json.dumps(data, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    _mkdir_private(destination.parent)
    temporary: str | None = None
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        temporary = None
        directory_fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _epoch(value: str | datetime | int | float) -> float:
    if isinstance(value, bool):
        raise ValueError("A finite timestamp with an explicit timezone is required")
    if isinstance(value, (int, float)):
        result = float(value)
    else:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
        if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("An explicit timestamp timezone is required")
        result = stamp.timestamp()
    if not math.isfinite(result):
        raise ValueError("A finite timestamp is required")
    return result


def _observation(value: str | None) -> None:
    if value is not None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("An original ISO timestamp or None is required")
        _epoch(value)


def _provider_record() -> dict[str, Any]:
    return {"stopped": False, "stop": None, "last_started_at": None, "seeds": {}}


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise ValueError("Non-finite JSON number")


def _validate(data: Any) -> None:
    if not isinstance(data, dict) or set(data) != {"version", "providers"} or type(data["version"]) is not int or data["version"] != 1 or not isinstance(data["providers"], dict):
        raise ValueError("Unsupported crawl ledger schema")
    for name, provider in data["providers"].items():
        if canonical_provider(name) != name or not isinstance(provider, dict) or set(provider) != {"stopped", "stop", "last_started_at", "seeds"}:
            raise ValueError("Invalid provider state")
        if type(provider["stopped"]) is not bool or not isinstance(provider["seeds"], dict):
            raise ValueError("Invalid provider state")
        last = provider["last_started_at"]
        if last is not None:
            if not isinstance(last, (int, float)) or isinstance(last, bool):
                raise ValueError("Invalid provider pacing timestamp")
            _epoch(last)
        stop = provider["stop"]
        if provider["stopped"] != (stop is not None):
            raise ValueError("Inconsistent provider stop state")
        if stop is not None:
            if not isinstance(stop, dict) or set(stop) != {"reason", "observed_at", "http_status", "source_url"} or not isinstance(stop["reason"], str) or not stop["reason"].strip():
                raise ValueError("Invalid provider denial")
            _observation(stop["observed_at"])
            if stop["http_status"] is not None and (type(stop["http_status"]) is not int or not 100 <= stop["http_status"] <= 599):
                raise ValueError("Invalid denial HTTP status")
            if stop["source_url"] is not None and not isinstance(stop["source_url"], str):
                raise ValueError("Invalid denial source")
        for seed_id, seed in provider["seeds"].items():
            if not isinstance(seed_id, str) or not seed_id.strip() or not isinstance(seed, dict) or set(seed) != {"attempts", "successes"}:
                raise ValueError("Invalid seed state")
            if not isinstance(seed["attempts"], list) or not isinstance(seed["successes"], list):
                raise ValueError("Invalid seed history")
            for attempt in seed["attempts"]:
                if not isinstance(attempt, dict) or set(attempt) != {"started_at"} or not isinstance(attempt["started_at"], str):
                    raise ValueError("Invalid attempt history")
                _observation(attempt["started_at"])
            for success in seed["successes"]:
                if not isinstance(success, dict) or set(success) != {"observed_at", "row"} or not isinstance(success["row"], dict):
                    raise ValueError("Invalid successful acquisition")
                _observation(success["observed_at"])


class CrawlState:
    """Exclusive private ledger. Snapshots cannot mutate durable state."""

    def __init__(self, path: str | Path = DEFAULT_STATE_PATH):
        self.path = Path(path).expanduser().absolute()
        self.lock_path = self.path.with_name(self.path.name + ".lock")
        self._lock_fd: int | None = None
        self._data: dict[str, Any] | None = None

    def __enter__(self) -> CrawlState:
        if self._lock_fd is not None:
            raise CrawlStateError("This crawl state is already open")
        _mkdir_private(self.path.parent)
        descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise CrawlStateLocked(f"Another crawl owns {self.lock_path}") from exc
            try:
                state_fd = os.open(self.path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
            except FileNotFoundError:
                data: dict[str, Any] = {"version": 1, "providers": {}}
                atomic_json_write(self.path, data)
            else:
                try:
                    with os.fdopen(state_fd, "r", encoding="utf-8") as stream:
                        data = json.load(stream, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
                    _validate(data)
                except (ValueError, TypeError, UnicodeError, OverflowError) as exc:
                    raise CrawlStateCorrupt(f"Invalid crawl ledger; refusing to reset {self.path}") from exc
            self._lock_fd = descriptor
            self._data = data
            return self
        except BaseException:
            os.close(descriptor)
            raise

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        if self._lock_fd is not None:
            descriptor, self._lock_fd = self._lock_fd, None
            self._data = None
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def _active(self) -> dict[str, Any]:
        if self._data is None or self._lock_fd is None:
            raise CrawlStateError("Use CrawlState inside its context manager")
        return self._data

    @property
    def data(self) -> dict[str, Any]:
        return copy.deepcopy(self._active())

    def provider(self, provider: str) -> dict[str, Any]:
        return copy.deepcopy(self._active()["providers"].get(canonical_provider(provider), _provider_record()))

    def is_stopped(self, provider: str) -> bool:
        return self.provider(provider)["stopped"]

    def _ensure_running(self, provider: str) -> str:
        name = canonical_provider(provider)
        if self.is_stopped(name):
            raise ProviderStopped(f"Provider {name} is persistently stopped")
        return name

    def _commit_provider(self, provider: str, record: dict[str, Any]) -> None:
        data = copy.deepcopy(self._active())
        data["providers"][canonical_provider(provider)] = record
        _validate(data)
        atomic_json_write(self.path, data)
        self._data = data

    def stop(self, provider: str, reason: str, observed_at: str | None, http_status: int | None = None, source_url: str | None = None) -> dict[str, Any]:
        record = self.provider(provider)
        if not record["stopped"]:
            record["stopped"] = True
            record["stop"] = {"reason": reason, "observed_at": observed_at, "http_status": http_status, "source_url": source_url}
            self._commit_provider(provider, record)
        return copy.deepcopy(record["stop"])

    def record_attempt(self, provider: str, seed_id: str, started_at: str) -> None:
        name = self._ensure_running(provider)
        _observation(started_at)
        if not isinstance(started_at, str):
            raise ValueError("An original attempt timestamp is required")
        epoch = _epoch(started_at)
        record = self.provider(name)
        seed = record["seeds"].setdefault(seed_id, {"attempts": [], "successes": []})
        seed["attempts"].append({"started_at": started_at})
        last = record["last_started_at"]
        record["last_started_at"] = epoch if last is None else max(last, epoch)
        self._commit_provider(name, record)

    def record_success(self, provider: str, seed_id: str, observed_at: str | None, row: dict[str, Any]) -> None:
        _observation(observed_at)
        if not isinstance(row, dict):
            raise ValueError("A successful observation must be a JSON object")
        record = self.provider(provider)
        seed = record["seeds"].setdefault(seed_id, {"attempts": [], "successes": []})
        evidence_hash = row.get("evidence_sha256")
        for previous in seed["successes"]:
            if previous["observed_at"] != observed_at:
                continue
            if isinstance(evidence_hash, str) and evidence_hash:
                if previous["row"].get("evidence_sha256") == evidence_hash:
                    return
            elif previous["row"] == row:
                return
        seed["successes"].append({"observed_at": observed_at, "row": copy.deepcopy(row)})
        self._commit_provider(provider, record)

    def should_skip(self, provider: str, seed_id: str, now: str | datetime | int | float, refresh_after_hours: float | None = None) -> bool:
        record = self.provider(provider)
        if record["stopped"]:
            return True
        successes = record["seeds"].get(seed_id, {}).get("successes", [])
        if not successes:
            return False
        if refresh_after_hours is None:
            return True
        if isinstance(refresh_after_hours, bool) or not isinstance(refresh_after_hours, (int, float)) or not math.isfinite(refresh_after_hours) or refresh_after_hours < 0:
            raise ValueError("An explicit finite nonnegative freshness window is required")
        observations = [_epoch(item["observed_at"]) for item in successes if item["observed_at"] is not None]
        if not observations:
            return False
        return _epoch(now) - max(observations) < refresh_after_hours * 3600

    def pace(self, provider: str, min_delay: float = 3, clock: Callable[[], float] = time.time, sleep: Callable[[float], Any] = time.sleep) -> float:
        """Wait against the last durable start; this method records no attempt."""
        name = self._ensure_running(provider)
        if isinstance(min_delay, bool) or not isinstance(min_delay, (int, float)) or not math.isfinite(min_delay) or min_delay < 0:
            raise ValueError("A finite nonnegative delay is required")
        delay = max(3.0, min_delay)
        last = self.provider(name)["last_started_at"]
        now = _epoch(clock())
        wait = max(0.0, last + delay - now) if last is not None else 0.0
        if wait:
            sleep(wait)
        return wait

    def begin_attempt(self, provider: str, seed_id: str, min_delay: float = 3, clock: Callable[[], float] = time.time, sleep: Callable[[float], Any] = time.sleep) -> str:
        """Pace, then durably record the actual start before network work."""
        self.pace(provider, min_delay=min_delay, clock=clock, sleep=sleep)
        now = _epoch(clock())
        last = self.provider(provider)["last_started_at"]
        if last is not None and now < last + max(3.0, min_delay):
            raise CrawlStateError("Clock did not advance through the required provider delay")
        started_at = datetime.fromtimestamp(now, timezone.utc).isoformat()
        self.record_attempt(provider, seed_id, started_at)
        return started_at
