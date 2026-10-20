#!/usr/bin/env python3
"""Reproduce a bounded Google audit without exporting a POI database.

At most six explicit, curated named places are eligible per run. No review text or image
bytes are retained. Stop at an access denial or consent gate. No proxy, private
Maps endpoint, browser token, initialization-array parsing, or account is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.providers.google import parse_visible_card
from scripts.providers.common import correlate, distance_m
from scripts.providers.crawl_state import CrawlState, CrawlStateError, DEFAULT_STATE_PATH, atomic_json_write

DEFAULT_CLOCK = time.time
DEFAULT_SLEEP = time.sleep

SEEDS = [
    ("bayterek", "osm-way-230401645", "Bayterek Astana Kazakhstan", 51.1282882, 71.4304546),
    ("national-museum", "osm-node-4894937300", "National Museum Republic Kazakhstan Astana", 51.1182297, 71.4693823),
    ("mega-silk-way", "osm-way-499328514", "MEGA Silk Way Astana Kazakhstan", 51.0890897, 71.4073303),
    ("cafela", "osm-node-5936638686", "Cafela Sarayshyq 9 Astana Kazakhstan", 51.1354068, 71.4305421),
    ("hazrat-sultan", "osm-way-240860325", "Hazrat Sultan Mosque Astana Kazakhstan", 51.1254256, 71.4721928),
    ("botanical-garden", "osm-way-1196402246", "Botanical Garden Astana Kazakhstan", 51.1061652, 71.4165705),
]
EXTRACT_VISIBLE_CARD = r"""(() => {
  const main = document.querySelector('[role=main]');
  const heading = main?.querySelector('h1');
  // An alternate-language name can sit between H1 and the rating. Restrict
  // extraction to direct siblings in this heading group, never the full panel
  // which can contain ratings for unrelated nearby businesses.
  const group = heading?.parentElement?.parentElement;
  const headerParts = group && group !== main && group.querySelectorAll('h1').length === 1 && !group.querySelector('h2,[role=tablist]')
    ? [...group.children].filter(x => x !== heading.parentElement).slice(0, 4)
    : [];
  const image = [...(main?.querySelectorAll('img') ?? [])].find(x => x.getBoundingClientRect().width > 100 && x.getBoundingClientRect().height > 100);
  const address = [...(main?.querySelectorAll('button[aria-label]') ?? [])].map(x => x.getAttribute('aria-label')).find(x => /^(Address|Адрес|Мекенжай):/i.test(x));
  return {
    url: location.href,
    title: document.title,
    document_status: (() => { const status = performance.getEntriesByType('navigation')[0]?.responseStatus; return Number.isInteger(status) && status >= 100 && status <= 599 ? status : null; })(),
    access_denied: location.pathname.startsWith('/sorry/') || Boolean(document.querySelector('form[action*="captcha"]')) || /unusual traffic|automated queries|подозрительный трафик/i.test(document.body.innerText),
    consent_required: location.hostname === 'consent.google.com',
    name: heading?.innerText ?? null,
    header_text: headerParts.length ? headerParts.map(x => x.innerText).join('\n') : null,
    rating_labels: headerParts.flatMap(x => [...x.querySelectorAll('[aria-label]')]).map(x => x.getAttribute('aria-label')),
    address: address?.replace(/^[^:]+:\s*/, '').trim() ?? null,
    primary_photo_links: image ? [image.currentSrc || image.src] : [],
    limited_version: /limited version|шектеулі нұсқасы|ограниченн\S* верси/i.test(main?.innerText ?? ''),
    source_links: [...(main?.querySelectorAll('a[href]') ?? [])].map(x => ({label: x.innerText || x.getAttribute('aria-label'), url: x.href})).filter(x => !/[?&](authuser|fp)=|accounts\.google|business\.google|google\.com\/local-listings/.test(x.url))
  };
})()"""


class ProviderAccessDenied(RuntimeError):
    def __init__(self, message: str, http_status: int | None = None):
        super().__init__(message)
        self.http_status = http_status


def google_robots_allows(robots: str, url: str) -> bool:
    """Longest matching rule, with an explicit allow required for known paths.

    The standard library's first-rule matching would incorrectly apply Google's
    broad /maps/ denial before its more specific /maps/search/ allowance.
    """
    parts = urlsplit(url)
    if parts.hostname != "www.google.com" or not parts.path.startswith(("/maps/search/", "/maps/place/")):
        return False
    path = parts.path + ("?" + parts.query if parts.query else "")
    active, in_rules, candidates = False, False, []
    for raw in robots.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if in_rules:
                if active:
                    break
                active, in_rules = False, False
            active = active or value == "*"
        elif key in {"allow", "disallow"}:
            in_rules = True
            if not active or not value:
                continue
            pattern = re.escape(value).replace(r"\*", ".*")
            if value.endswith("$"):
                pattern = pattern[:-2] + "$"
            if re.match(pattern, path):
                candidates.append((len(value.replace("*", "").rstrip("$")), key == "allow"))
    return bool(candidates and max(candidates)[1])


def preflight(url: str) -> dict:
    """Check ordinary HTTP access before attempting browser rendering."""
    request = Request(url, headers={"User-Agent": "Qala-Research/1.0 (bounded public source audit)"})
    try:
        with urlopen(request, timeout=25) as response:
            body = response.read(300000)
            result = {"http_status": response.status, "http_evidence_sha256": hashlib.sha256(body).hexdigest()}
    except HTTPError as error:
        if error.code in {401, 403, 429}:
            raise ProviderAccessDenied(f"HTTP {error.code}; provider stopped without browser retry", http_status=error.code) from error
        raise
    if b"unusual traffic" in body.lower() or b"/sorry/index" in body.lower():
        raise ProviderAccessDenied("HTTP access challenge; provider stopped without browser retry")
    return result


def validate_seeds(raw: list[dict] | None, catalogue: list[dict]) -> list[dict]:
    """Only explicit named local POIs qualify; coordinates come from our corpus."""
    if raw is None:
        raw = [{"slug": slug, "poi_id": poi_id, "query": query} for slug, poi_id, query, _, _ in SEEDS]
    if not isinstance(raw, list) or not 1 <= len(raw) <= 6:
        raise ValueError("Provide between one and six explicit curated seeds; bulk grids are unsupported")
    local = {item["id"]: item for item in catalogue}
    result, identifiers, slugs = [], set(), set()
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("poi_id"), str):
            raise ValueError("Each seed requires an existing local poi_id and a named venue query")
        poi_id = item["poi_id"]
        poi = local.get(poi_id)
        if poi is None:
            raise ValueError(f"Unknown local POI ID: {poi_id}")
        name = poi.get("name")
        if not isinstance(name, str) or len(name.strip()) < 2 or poi.get("name_derived") is True:
            raise ValueError(f"Seed {poi_id} must identify an explicitly named place")
        query = item.get("query")
        if (not isinstance(query, str) or not 5 <= len(query.strip()) <= 240
                or any(ord(character) < 32 for character in query)
                or "://" in query or "*" in query or not re.search(r"[^\W\d_]{3}", query)):
            raise ValueError(f"Seed {poi_id} needs a sensible specific place name/address query")
        slug = item.get("slug", re.sub(r"[^a-z0-9_-]", "-", poi_id.lower()))
        if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", slug):
            raise ValueError("Seed slugs must be unique safe lowercase filenames")
        if poi_id in identifiers or slug in slugs:
            raise ValueError("Duplicate seed identities or output slugs are unsupported")
        identifiers.add(poi_id)
        slugs.add(slug)
        result.append({"slug": slug, "poi_id": poi_id, "query": query.strip(), "name": name, "lat": poi["lat"], "lon": poi["lon"]})
    return result


def _read_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    value = json.loads(path.read_text())
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"Existing acquisition output is invalid; refusing to replace it: {path}")
    return value


def _row_key(row: dict) -> tuple:
    return (row.get("provider"), row.get("provider_id"), row.get("observed_at"), row.get("evidence_sha256"))


def _seed_distance(row: dict, seed: dict) -> float | None:
    """Entity coordinates are required; an absent or remote point is no hit."""
    lat, lon = row.get("lat"), row.get("lon")
    for latitude, longitude in ((lat, lon), (seed.get("lat"), seed.get("lon"))):
        if (isinstance(latitude, bool) or isinstance(longitude, bool)
                or not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float))
                or not math.isfinite(latitude) or not math.isfinite(longitude)
                or not -90 <= latitude <= 90 or not -180 <= longitude <= 180):
            return None
    return distance_m(lat, lon, seed["lat"], seed["lon"])


def _seed_observation_eligible(row: dict, seed: dict) -> bool:
    """An unresolved translation can be nearby; it cannot be anywhere."""
    delta = _seed_distance(row, seed)
    matches = row.get("matched_poi_ids") or []
    return (row.get("provider") == "google" and delta is not None and delta <= 200
            and (not matches or seed["poi_id"] in matches))


def _eligible_successes(state: CrawlState, seed: dict) -> list[dict]:
    successes = state.provider("google").get("seeds", {}).get(seed["poi_id"], {}).get("successes", [])
    return [entry for entry in successes if isinstance(entry.get("row"), dict)
            and _seed_observation_eligible(entry["row"], seed)]


def _seed_is_cached(state: CrawlState, seed: dict, now: float, refresh_after_hours: float | None) -> bool:
    # A legacy remote success must not suppress a seed or extend the freshness
    # of a different, older valid observation. Preserve history without using
    # ineligible entries as evidence that this requested place was acquired.
    successes = _eligible_successes(state, seed)
    if not successes:
        return False
    if refresh_after_hours is None:
        return True
    acquired = [datetime.fromisoformat(entry["observed_at"].replace("Z", "+00:00")).timestamp()
                for entry in successes if entry.get("observed_at") is not None]
    return bool(acquired and now - max(acquired) < refresh_after_hours * 3600)


def _restore_successes(state: CrawlState, selected: list[dict], rows: list[dict], probes: list[dict]) -> None:
    """Import original dated acquisition records, never a newly generated date."""
    seeds = {item["poi_id"]: item for item in selected}
    existing = {_row_key(row) for row in rows}
    for probe in probes:
        seed_id = probe.get("requested_poi_id")
        if seed_id not in seeds or probe.get("status") != "visible_card_observed":
            continue
        row = next((row for row in rows if row.get("provider") == "google"
                    and row.get("provider_id") == probe.get("provider_id")
                    and row.get("observed_at") == probe.get("observed_at")), None)
        if row is None or not _seed_observation_eligible(row, seeds[seed_id]):
            continue
        previous = state.provider("google").get("seeds", {}).get(seed_id, {}).get("successes", [])
        if not any(_row_key(entry.get("row", {})) == _row_key(row) for entry in previous):
            state.record_success("google", seed_id, observed_at=row.get("observed_at"), row=row)
    for seed_id in seeds:
        successes = _eligible_successes(state, seeds[seed_id])
        for entry in successes:
            row = entry.get("row")
            if isinstance(row, dict) and _row_key(row) not in existing:
                rows.append(row)
                existing.add(_row_key(row))


def run_capture(browser_cli: str, output: Path, limit: int = 6, screenshots: bool = False, *,
                seeds: list[dict] | None = None, language: str = "ru", state_path: Path | None = None,
                refresh_after_hours: float | None = None, delay_seconds: float = 3,
                clock=None, sleep=None, catalogue: list[dict] | None = None) -> dict:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 6:
        raise ValueError("The audit is capped at six explicit named seeds")
    if language not in {"ru", "en", "kk"}:
        raise ValueError("Public UI language must be ru, en or kk")
    if isinstance(delay_seconds, bool) or not isinstance(delay_seconds, (int, float)) or not math.isfinite(delay_seconds) or delay_seconds < 3:
        raise ValueError("Request starts must be paced by at least three seconds")
    if refresh_after_hours is not None and (isinstance(refresh_after_hours, bool) or not isinstance(refresh_after_hours, (int, float)) or not math.isfinite(refresh_after_hours) or refresh_after_hours <= 0):
        raise ValueError("An explicit freshness window must be a positive number of hours")
    clock, sleep = clock or DEFAULT_CLOCK, sleep or DEFAULT_SLEEP
    output = Path(output)
    if catalogue is None:
        catalogue = json.loads((Path(__file__).resolve().parents[1] / "data/pois.json").read_text())["pois"]
    selected = validate_seeds(seeds, catalogue)
    base = [browser_cli, "--session", "qala-google-crawl"]
    with CrawlState(state_path or DEFAULT_STATE_PATH) as state:
        rows, probes = _read_records(output / "rows.json"), _read_records(output / "browser-probes.json")
        if state.is_stopped("google"):
            return {"rows": rows, "probes": probes, "status": "provider_stopped", "new_attempts": 0, "skipped_seed_ids": [], "stop": state.provider("google").get("stop")}
        _restore_successes(state, selected, rows, probes)
        pending, skipped = [], []
        for item in selected:
            if _seed_is_cached(state, item, now=clock(), refresh_after_hours=refresh_after_hours):
                skipped.append(item["poi_id"])
            else:
                pending.append(item)
        if not pending:
            if rows:
                atomic_json_write(output / "rows.json", rows)
                atomic_json_write(output / "browser-probes.json", probes)
            return {"rows": rows, "probes": probes, "status": "cached", "new_attempts": 0, "skipped_seed_ids": skipped}

        # One shared lock and persistent request clock cover HTTP and browser
        # starts; private API failures never seed this public-site stop state.
        robots_started = state.begin_attempt("google", "__robots__", min_delay=delay_seconds, clock=clock, sleep=sleep)
        try:
            with urlopen(Request("https://www.google.com/robots.txt", headers={"User-Agent": "Qala-Research/1.0"}), timeout=25) as response:
                robots = response.read(30000).decode("utf-8", "replace")
            output.mkdir(parents=True, exist_ok=True)
            robots_path = output / ("google-robots-" + re.sub(r"[^0-9]", "", robots_started) + ".txt")
            robots_path.write_text(robots)
        except Exception as error:
            denied = isinstance(error, HTTPError) and error.code in {401, 403, 429}
            if denied:
                state.stop("google", str(error), robots_started, http_status=error.code, source_url="https://www.google.com/robots.txt")
            probe = {"status": "provider_stopped" if denied else "robots_unavailable", "observed_at": robots_started, "error": type(error).__name__ + ": " + str(error)[:300]}
            probes.append(probe)
            atomic_json_write(output / "rows.json", rows)
            atomic_json_write(output / "browser-probes.json", probes)
            return {"rows": rows, "probes": probes, "status": probe["status"], "new_attempts": 0, "skipped_seed_ids": skipped}

        attempts, successes, failures, stopped = 0, 0, 0, False
        for item in pending:
            if attempts >= limit:
                break
            slug, poi_id = item["slug"], item["poi_id"]
            url = "https://www.google.com/maps/search/?" + urlencode({"api": 1, "query": item["query"], "hl": language})
            started = state.begin_attempt("google", poi_id, min_delay=delay_seconds, clock=clock, sleep=sleep)
            attempts += 1
            probe = {"slug": slug, "query_url": url, "requested_poi_id": poi_id, "requested_lat": item["lat"], "requested_lon": item["lon"], "observed_at": started, "language": language}
            try:
                if not google_robots_allows(robots, url):
                    raise ProviderAccessDenied("No explicit robots allowance for this Maps path; provider stopped")
                preflight_evidence = preflight(url)
                probe["preflight_http_status"] = preflight_evidence.get("http_status")
                if "http_evidence_sha256" in preflight_evidence:
                    probe["http_evidence_sha256"] = preflight_evidence["http_evidence_sha256"]
                browser_started = state.begin_attempt("google", poi_id + "::browser", min_delay=delay_seconds, clock=clock, sleep=sleep)
                probe["observed_at"] = browser_started
                result = subprocess.run(base + ["open", url], capture_output=True, text=True, timeout=45, check=True)
                probe["open_exit"] = result.returncode
                probe["open_summary"] = result.stdout[:350]
                wait_timed_out = False
                try:
                    waited = subprocess.run(base + ["wait", "--fn", "document.querySelector('[role=main] h1') !== null && location.pathname.includes('/maps/place/')"], capture_output=True, text=True, timeout=28)
                    wait_timed_out = waited.returncode != 0
                except subprocess.TimeoutExpired:
                    wait_timed_out = True
                if wait_timed_out:
                    probe["readiness_wait_timed_out"] = True
                try:
                    result = subprocess.run(base + ["eval", "--stdin"], input=EXTRACT_VISIBLE_CARD, capture_output=True, text=True, timeout=15, check=True)
                    card = json.loads(result.stdout)
                    if not isinstance(card, dict):
                        raise ValueError("Visible-page inspection returned no metadata object")
                except Exception as error:
                    if wait_timed_out:
                        raise ProviderAccessDenied("Readiness timed out and browser denial/status inspection was unavailable; defer provider without retry") from error
                    raise
                document_status = card.get("document_status")
                if isinstance(document_status, bool) or not isinstance(document_status, int) or not 100 <= document_status <= 599:
                    document_status = None
                probe["browser_document_http_status"] = document_status
                if document_status in {401, 403, 429}:
                    raise ProviderAccessDenied(f"Browser document HTTP {document_status}; provider stopped without retry", http_status=document_status)
                if card.get("access_denied") or card.get("consent_required"):
                    raise ProviderAccessDenied("Browser access challenge or consent gate; provider stopped without retry")
                if wait_timed_out and document_status is None:
                    raise ProviderAccessDenied("Readiness timed out and browser document status remains unknown; defer provider without claiming an HTTP denial")
                if not google_robots_allows(robots, card.get("url", "")):
                    raise ProviderAccessDenied("Canonical card path lacks explicit robots allowance; provider stopped")
                card.update({"observed_at": probe["observed_at"], "http_status": document_status})
                evidence_name = slug + "-" + re.sub(r"[^0-9]", "", probe["observed_at"]) + "-visible.json"
                atomic_json_write(output / evidence_name, card)
                row = correlate(parse_visible_card(card), catalogue)
                delta = _seed_distance(row, item)
                if delta is not None:
                    probe["distance_from_seed_m"] = round(delta, 1)
                probe["identity_method"] = "Requested seed is candidate context only; exact catalogue name/alias and nearby entity coordinates are required for an automatic match."
                probe["identity_requires_review"] = poi_id not in row["matched_poi_ids"]
                wrong_entity = bool(row["matched_poi_ids"]) and poi_id not in row["matched_poi_ids"]
                eligible = _seed_observation_eligible(row, item)
                if _row_key(row) not in {_row_key(previous) for previous in rows}:
                    rows.append(row)
                outcome = ("wrong_entity_selected" if wrong_entity else "entity_coordinates_missing" if delta is None
                           else "entity_outside_seed_bounds" if delta > 200 else "visible_card_observed")
                probe.update({"status": outcome, "provider_id": row["provider_id"], "name": row["name"], "rating": row["rating"], "rating_count": row["rating_count"], "photo_link_count": len(row["photo_source_links"]), "evidence_path": evidence_name})
                if eligible:
                    state.record_success("google", poi_id, observed_at=row["observed_at"], row=row)
                    successes += 1
                else:
                    failures += 1
                if screenshots:
                    subprocess.run(base + ["screenshot", str((output / (evidence_name.removesuffix("-visible.json") + "-public-card.png")).resolve())], capture_output=True, text=True, timeout=15)
            except Exception as error:
                stopped = isinstance(error, ProviderAccessDenied) or isinstance(error, HTTPError) and error.code in {401, 403, 429}
                probe.update({"status": "provider_stopped" if stopped else "capture_unavailable", "error": type(error).__name__ + ": " + str(error)[:300]})
                failures += 1
                if stopped:
                    status = getattr(error, "http_status", None) or probe.get("browser_document_http_status") or (error.code if isinstance(error, HTTPError) else None)
                    state.stop("google", probe["error"], probe["observed_at"], http_status=status, source_url=url)
            probes.append(probe)
            atomic_json_write(output / "rows.json", rows)
            atomic_json_write(output / "browser-probes.json", probes)
            print(json.dumps(probe, ensure_ascii=False), flush=True)
            if stopped:
                break
        return {"rows": rows, "probes": probes, "status": "provider_stopped" if stopped else "partial" if failures else "complete", "new_attempts": attempts, "new_successes": successes, "new_failures": failures, "skipped_seed_ids": skipped}


def main() -> None:
    parser = argparse.ArgumentParser(description="Resumable, paced Google public-card audit; explicit named places only, no review prose or downloaded photos.")
    parser.add_argument("--browser-cli", default=os.environ.get("AGENT_BROWSER_BIN") or shutil.which("agent-browser"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/provider-crawl/google"))
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH, help="Private shared provider ledger; access denials persist across runs")
    parser.add_argument("--seeds", type=Path, help="JSON list of at most six explicit {poi_id,query,slug?} entries")
    parser.add_argument("--language", choices=["ru", "en", "kk"], default="ru")
    parser.add_argument("--refresh-after-hours", type=float, help="Explicit age threshold for successful seeds; does not clear an access denial")
    parser.add_argument("--delay-seconds", type=float, default=3, help="Minimum gap between explicit top-level request/navigation starts; at least3")
    parser.add_argument("--limit", type=int, default=6, choices=range(1, 7))
    parser.add_argument("--screenshots", action="store_true")
    args = parser.parse_args()
    if not args.browser_cli:
        parser.error("Set --browser-cli to the installed agent-browser executable")
    try:
        seeds = json.loads(args.seeds.read_text()) if args.seeds else None
        result = run_capture(args.browser_cli, args.output, args.limit, args.screenshots, seeds=seeds, language=args.language,
                             state_path=args.state, refresh_after_hours=args.refresh_after_hours, delay_seconds=args.delay_seconds)
    except (ValueError, OSError, CrawlStateError) as error:
        parser.error(str(error))
    print(json.dumps({"status": result["status"], "new_attempts": result["new_attempts"], "skipped_seed_ids": result["skipped_seed_ids"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
