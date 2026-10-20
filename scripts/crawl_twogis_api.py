#!/usr/bin/env python3
"""Bounded, diagnostics-only audit of the official 2GIS Places API.

Explicit named local POIs only. API products remain in memory for one request;
no provider names, IDs, coordinates, ratings, photos, contacts or review text
are persisted. A private completion ledger stores only local seed fingerprints
and sanitized diagnostics. It never serves cached API products to the app.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.providers.common import distance_m, local_names, normalized_name
from scripts.providers.crawl_state import CrawlState, CrawlStateError, DEFAULT_STATE_PATH, atomic_json_write

PROVIDER = "2gis_catalog_api"
ENDPOINT = "https://catalog.api.2gis.com/3.0/items"
FIELDS = "items.point,items.name_ex,items.reviews,items.schedule,items.flags"
MAX_BYTES = 2 * 1024 * 1024
LOCALES = {"ru": "ru_KZ", "kk": "kk_KZ", "en": "en_RU"}
DIAGNOSTIC_KEYS = {"local_poi_id", "seed_fingerprint", "observed_at", "http_status", "meta_code",
                   "response_bytes", "response_sha256", "identity_status", "identity_verified",
                   "candidate_count", "nearby_candidate_count", "exact_alias_candidate_count",
                   "result_truncated", "field_presence_counts", "identity_method", "status", "error_code"}


class ProviderFailure(RuntimeError):
    """Only a fixed error code is exposed, never request URLs or provider prose."""
    def __init__(self, code: str, *, http_status=None, meta_code=None):
        super().__init__(code)
        self.code, self.http_status, self.meta_code = code, http_status, meta_code


def _point(item: dict) -> tuple[float, float] | None:
    point = item.get("point")
    if not isinstance(point, dict):
        return None
    lat, lon = point.get("lat"), point.get("lon")
    if (isinstance(lat, bool) or isinstance(lon, bool) or not isinstance(lat, (float, int))
            or not isinstance(lon, (float, int)) or not math.isfinite(lat) or not math.isfinite(lon)
            or not -90 <= lat <= 90 or not -180 <= lon <= 180):
        return None
    return lat, lon


def _candidate_names(item: dict) -> set[str]:
    values = [item.get("name")]
    extended = item.get("name_ex")
    if isinstance(extended, dict):
        values.append(extended.get("primary"))
    return {normalized_name(value) for value in values if isinstance(value, str) and value.strip()}


def identity_diagnostics(items: list[dict], poi: dict, catalogue: list[dict], *, total: int | None = None) -> dict:
    """Inspect identities transiently; return counts/decisions, never API facts."""
    seen, nearby, exact, missing_exact = set(), [], [], False
    coverage = {"point": 0, "name_ex_primary": 0, "reviews": 0, "schedule": 0, "photos_flag": 0,
                "general_rating": 0, "general_review_count": 0, "general_review_count_with_stars": 0}
    aliases = local_names(poi)
    for item in items:
        if not isinstance(item, dict):
            continue
        identifier = item.get("id")
        if not isinstance(identifier, str) or not re.fullmatch(r"[0-9]{5,25}", identifier) or identifier in seen:
            continue
        seen.add(identifier)
        names, point = _candidate_names(item), _point(item)
        if point:
            coverage["point"] += 1
        if isinstance(item.get("name_ex"), dict) and isinstance(item["name_ex"].get("primary"), str):
            coverage["name_ex_primary"] += 1
        for field in ("reviews", "schedule"):
            if isinstance(item.get(field), dict):
                coverage[field] += 1
        if isinstance(item.get("flags"), dict) and isinstance(item["flags"].get("photos"), bool):
            coverage["photos_flag"] += 1
        reviews = item.get("reviews")
        if isinstance(reviews, dict):
            for field in ("general_rating", "general_review_count", "general_review_count_with_stars"):
                if field in reviews:
                    coverage[field] += 1
        exact_name = bool(names & aliases)
        if point is None:
            missing_exact = missing_exact or exact_name
            continue
        lat, lon = point
        if distance_m(lat, lon, poi["lat"], poi["lon"]) > 200:
            continue
        nearby.append(item)
        if exact_name:
            local_matches = [local["id"] for local in catalogue if names & local_names(local)
                             and distance_m(lat, lon, local["lat"], local["lon"]) <= 200]
            exact.append((item, local_matches))
    truncated = total is not None and total > len(items)
    ambiguous = len(exact) > 1 or any(matches != [poi["id"]] for _, matches in exact)
    verified = len(exact) == 1 and not ambiguous and not missing_exact and not truncated
    outcome = ("verified_identity" if verified else "ambiguous_identity" if ambiguous else "truncated_result" if truncated
               else "missing_entity_coordinates" if missing_exact else "tentative_identity" if nearby else "no_nearby_match")
    return {"identity_status": outcome, "identity_verified": verified, "candidate_count": len(seen),
            "nearby_candidate_count": len(nearby), "exact_alias_candidate_count": len(exact), "result_truncated": truncated,
            "field_presence_counts": coverage,
            "identity_method": "Exact existing local alias or name_ex.primary; actual entity distance <=200m; unique provider and local branch required."}


def _seeds(raw: list, catalogue: list[dict]) -> list[dict]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= 20:
        raise ValueError("Provide one to twenty explicit named local POI IDs; no bulk grids")
    local = {poi["id"]: poi for poi in catalogue}
    result, seen = [], set()
    for seed in raw:
        identifier = seed if isinstance(seed, str) else seed.get("poi_id") if isinstance(seed, dict) else None
        poi = local.get(identifier) if isinstance(identifier, str) else None
        if poi is None or identifier in seen:
            raise ValueError("Each seed must be a unique existing local POI ID")
        if not isinstance(poi.get("name"), str) or len(poi["name"].strip()) < 2 or poi.get("name_derived") is True:
            raise ValueError("Each seed must identify an explicitly named place")
        if _point({"point": {"lat": poi.get("lat"), "lon": poi.get("lon")}}) is None:
            raise ValueError("Local seed coordinates are invalid")
        seen.add(identifier)
        result.append(poi)
    return result


def seed_fingerprint(poi: dict) -> str:
    own = {"id": poi["id"], "lat": poi["lat"], "lon": poi["lon"], "names": sorted(local_names(poi)), "address": poi.get("address")}
    return hashlib.sha256(json.dumps(own, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()


def request_parameters(poi: dict, key: str, language: str) -> dict:
    names = poi.get("names") if isinstance(poi.get("names"), dict) else {}
    name = names.get(language) or poi["name"]
    parts = [name]
    if isinstance(poi.get("address"), str) and poi["address"].strip():
        parts.append(poi["address"].strip())
    parts.append("Астана")
    return {"key": key, "q": ", ".join(parts)[:500], "point": f"{poi['lon']},{poi['lat']}", "radius": 200,
            "type": "branch", "page_size": 5, "fields": FIELDS, "locale": LOCALES[language]}


def fetch_diagnostics(client: httpx.Client, poi: dict, catalogue: list[dict], key: str, language: str) -> dict:
    """Exactly one official request; bounded response, no redirects or retries."""
    digest, buffer = hashlib.sha256(), bytearray()
    try:
        with client.stream("GET", ENDPOINT, params=request_parameters(poi, key, language), follow_redirects=False) as response:
            status = response.status_code
            if status != 200:
                raise ProviderFailure("redirect_refused" if 300 <= status < 400 else "http_error", http_status=status)
            length = response.headers.get("Content-Length")
            if length and length.isdigit() and int(length) > MAX_BYTES:
                raise ProviderFailure("response_too_large", http_status=status)
            for chunk in response.iter_bytes():
                if len(buffer) + len(chunk) > MAX_BYTES:
                    raise ProviderFailure("response_too_large", http_status=status)
                buffer.extend(chunk)
                digest.update(chunk)
    except ProviderFailure:
        raise
    except httpx.HTTPError:
        raise ProviderFailure("transport_error") from None
    try:
        payload = json.loads(buffer)
    except (ValueError, UnicodeError):
        raise ProviderFailure("invalid_json", http_status=200) from None
    meta = payload.get("meta") if isinstance(payload, dict) else None
    code = meta.get("code") if isinstance(meta, dict) else None
    if isinstance(code, bool) or not isinstance(code, int) or code != 200:
        raise ProviderFailure("api_meta_error", http_status=200, meta_code=code if type(code) is int else None)
    result = payload.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("items"), list):
        raise ProviderFailure("invalid_result", http_status=200, meta_code=200)
    total = result.get("total")
    total = total if type(total) is int and total >= 0 else None
    diagnostics = identity_diagnostics(result["items"], poi, catalogue, total=total)
    return {"http_status": 200, "meta_code": 200, "response_bytes": len(buffer), "response_sha256": digest.hexdigest(), **diagnostics}


def _read_output(path: Path) -> list[dict]:
    if not path.exists():
        return []
    value = json.loads(path.read_text())
    if (not isinstance(value, dict) or value.get("provider") != PROVIDER or not isinstance(value.get("records"), list)
            or any(not isinstance(row, dict) or set(row) - DIAGNOSTIC_KEYS for row in value.get("records", []))):
        raise ValueError("Existing diagnostics are invalid; refusing to replace them")
    return value["records"]


def run_audit(seeds: list, output: Path, *, key: str, catalogue: list[dict] | None = None, state_path: Path = DEFAULT_STATE_PATH,
              limit: int = 20, delay_seconds: float = 3, language: str = "ru", client=None, clock=time.time, sleep=time.sleep) -> dict:
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("Per-run query limit must be one to twenty")
    if isinstance(delay_seconds, bool) or not isinstance(delay_seconds, (int, float)) or not math.isfinite(delay_seconds) or delay_seconds < 1:
        raise ValueError("Delay must be at least one second")
    if language not in LOCALES:
        raise ValueError("Language must be ru, kk or en")
    if not isinstance(key, str) or not key.strip():
        raise ValueError("TWOGIS_API_KEY is not configured")
    if catalogue is None:
        catalogue = json.loads((ROOT / "data/pois.json").read_text())["pois"]
    selected, path = _seeds(seeds, catalogue), Path(output)
    with CrawlState(state_path) as state:
        records = _read_output(path)
        def publish(status, attempts=0, skipped=None):
            value = {"schema_version": 1, "provider": PROVIDER, "endpoint": ENDPOINT, "mode": "diagnostics_only",
                     "status": status, "checked_at": datetime.fromtimestamp(clock(), timezone.utc).isoformat(),
                     "new_queries": attempts, "skipped_local_poi_ids": skipped or [], "records": records,
                     "api_products_persisted": False, "crosswalk_persisted": False, "completed_response_cache": False}
            atomic_json_write(path, value)
            return value
        if state.is_stopped(PROVIDER):
            return publish("provider_stopped")
        pending, skipped = [], []
        for poi in selected:
            fingerprint = seed_fingerprint(poi)
            successes = state.provider(PROVIDER).get("seeds", {}).get(poi["id"], {}).get("successes", [])
            previous = [entry["row"] for entry in successes if entry["row"].get("seed_fingerprint") == fingerprint
                        and not set(entry["row"]) - DIAGNOSTIC_KEYS]
            if previous:
                for row in previous:
                    if row not in records:
                        records.append(row)
                skipped.append(poi["id"])
            else:
                pending.append((poi, fingerprint))
        if not pending:
            return publish("cached_diagnostics_only", skipped=skipped)
        owned = client is None
        manager = httpx.Client(transport=httpx.HTTPTransport(retries=0), timeout=httpx.Timeout(15, connect=5), follow_redirects=False, trust_env=False) if owned else nullcontext(client)
        with manager as api:
            queries = 0
            for poi, fingerprint in pending[:limit]:
                # Shared ledger enforces three seconds, exceeding the API audit's
                # one-second floor and preventing concurrent provider campaigns.
                acquired = state.begin_attempt(PROVIDER, poi["id"], min_delay=max(3, delay_seconds), clock=clock, sleep=sleep)
                queries += 1
                record = {"local_poi_id": poi["id"], "seed_fingerprint": fingerprint, "observed_at": acquired}
                try:
                    record.update(fetch_diagnostics(api, poi, catalogue, key.strip(), language))
                    record["status"] = "diagnostic_complete"
                    state.record_success(PROVIDER, poi["id"], acquired, record)
                except ProviderFailure as error:
                    record.update({"status": "provider_stopped", "error_code": error.code, "http_status": error.http_status, "meta_code": error.meta_code})
                    # Store only fixed codes and the keyless official endpoint.
                    state.stop(PROVIDER, error.code, acquired, http_status=error.http_status, source_url=ENDPOINT)
                records.append(record)
                result = publish("provider_stopped" if state.is_stopped(PROVIDER) else "complete", queries, skipped)
                if state.is_stopped(PROVIDER):
                    return result
        return publish("complete" if len(pending) <= limit else "partial", queries, skipped)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", required=True, type=Path, help="JSON list of local poi_id entries; API queries derive solely from catalogue names/coordinates")
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts/provider-crawl/2gis-api/diagnostics.json")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--limit", type=int, default=20, choices=range(1, 21))
    parser.add_argument("--delay-seconds", type=float, default=3)
    parser.add_argument("--language", choices=sorted(LOCALES), default="ru")
    args = parser.parse_args()
    config = dotenv_values(ROOT / ".env", interpolate=False)
    configured = os.environ["TWOGIS_API_KEY"] if "TWOGIS_API_KEY" in os.environ else config.get("TWOGIS_API_KEY")
    key = configured.strip() if isinstance(configured, str) else ""
    try:
        result = run_audit(json.loads(args.seeds.read_text()), args.out, key=key or "", state_path=args.state,
                           limit=args.limit, delay_seconds=args.delay_seconds, language=args.language)
    except (OSError, ValueError, CrawlStateError):
        parser.exit(2, "API audit configuration/state error; no credential or provider payload is logged.\n")
    print(json.dumps({"status": result["status"], "new_queries": result["new_queries"], "diagnostic_records": len(result["records"])}))


if __name__ == "__main__":
    main()
