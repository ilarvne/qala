#!/usr/bin/env python3
"""Bounded, explicit live readiness checks; credentials and bodies stay private.

This verifies reachability and small real operations, not production capacity.
Run check_alemplus.py separately for its bounded LLM/reranker/STT fixtures.
ElevenLabs account/model checks are supplied as a separate read-only receipt;
this script never synthesizes speech or starts a paid voice conversation.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.events import URL as EVENTS_URL, ROBOTS_URL, parse_calendar
from backend.public_http import USER_AGENT
from backend.weather import CITY, FIELDS, URL as WEATHER_URL, parse_forecast


def receipt(path: Path) -> dict:
    if not path.is_file():
        return {"available": False, "path": str(path.relative_to(ROOT))}
    return {"available": True, "path": str(path.relative_to(ROOT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "data": json.loads(path.read_text())}


def trusted_map_url(url: str) -> bool:
    parsed = urlsplit(url)
    return parsed.scheme == "https" and parsed.hostname == "tiles.openfreemap.org" and not parsed.username and not parsed.password and not parsed.query


async def check(args):
    parsed = urlsplit(args.base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SystemExit("The app endpoint must be an HTTP loopback origin")
    load_dotenv(ROOT / ".env")
    raw = (ROOT / "data/pois.json").read_bytes()
    dataset = json.loads(raw)
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(), "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "poi_count": len(dataset["pois"]), "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scope": "One bounded operation per public service, three explicit 2GIS profiles, one OpenAI authentication read; no retry, TTS generation or conversation initiation.",
        "privacy": "No credentials, signed URLs, upstream bodies, reviews, generated text or transcripts retained. Local app calls are counted separately from provider calls.",
        "quota_rule": "Successful requests prove current availability only. No remaining balance is inferred when the provider does not expose an account quota in this probe.",
        "calls": [], "services": {}, "external_receipts": {},
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=5), follow_redirects=False,
                                 headers={"User-Agent": USER_AGENT}, trust_env=False) as client:
        async def fetch(service, method, url, *, max_bytes=2_000_000, **kwargs):
            start = time.perf_counter()
            item = {"service": service, "method": method, "target": "local app" if url.startswith(args.base_url) else "provider"}
            body, response_headers = None, {}
            try:
                async with client.stream(method, url, **kwargs) as response:
                    item["http_status"] = response.status_code
                    parts, size = [], 0
                    async for part in response.aiter_bytes():
                        size += len(part)
                        if size > max_bytes:
                            raise ValueError("response_size_limit")
                        parts.append(part)
                    body = b"".join(parts)
                    response_headers = response.headers
                    item["response_bytes"] = size
            except Exception as error:
                item["error_type"] = type(error).__name__
            item["elapsed_ms"] = round((time.perf_counter() - start) * 1000)
            report["calls"].append(item)
            return item, body, response_headers

        item, body, _ = await fetch("app", "GET", args.base_url + "/api/health")
        health = json.loads(body) if item.get("http_status") == 200 and body else {}
        report["services"]["app"] = {"available": health.get("status") == "ok", "runtime_poi_count": health.get("poi_count"),
                                           "dataset_count_matches": health.get("poi_count") == len(dataset["pois"]),
                                           "mode": health.get("mode"), "embedding_mode": health.get("embedding_mode")}

        configured = bool(os.getenv("OPENAI_API_KEY"))
        report["services"]["openai"] = {"configured": configured, "quota": "not_exposed_by_models_read", "active_runtime_provider": False}
        if configured:
            item, _, _ = await fetch("openai", "GET", "https://api.openai.com/v1/models", headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]})
            report["services"]["openai"].update(http_status=item.get("http_status"), available=item.get("http_status") == 200,
                                                         authentication_rejected=item.get("http_status") == 401)

        profiles = []
        configured = bool(os.getenv("TWOGIS_API_KEY"))
        if configured:
            for poi_id in ("osm-node-4894937300", "osm-way-230401645", "osm-node-10170946741"):
                item, body, headers = await fetch("2gis", "GET", args.base_url + f"/api/pois/{poi_id}/sources/2gis", params={"language": "ru"})
                payload = json.loads(body) if item.get("http_status") == 200 and body else {}
                profiles.append({"poi_id": poi_id, "http_status": item.get("http_status"), "status": payload.get("status"),
                                 "no_store": headers.get("cache-control") == "no-store"})
        report["services"]["2gis"] = {"configured": configured, "available": bool(profiles) and all(p["status"] == "matched" for p in profiles),
                                           "profiles": profiles, "quota": "provider_account_balance_not_exposed", "persistence": "transient_display_only"}

        item, body, _ = await fetch("weather", "GET", WEATHER_URL, params={"latitude": CITY[0], "longitude": CITY[1],
                                       "hourly": ",".join(FIELDS), "timezone": "Asia/Almaty", "timeformat": "unixtime",
                                       "wind_speed_unit": "kmh", "forecast_days": 16, "past_days": 1})
        rows = []
        try:
            rows = parse_forecast(json.loads(body)) if item.get("http_status") == 200 and body else []
        except (ValueError, TypeError, KeyError):
            pass
        report["services"]["weather"] = {"available": bool(rows), "http_status": item.get("http_status"), "validated_hourly_rows": len(rows),
                                               "fixed_city_only": True, "quota": "anonymous_balance_not_exposed"}

        robots, body, _ = await fetch("events", "GET", ROBOTS_URL, max_bytes=100_000)
        allowed, records = False, []
        if robots.get("http_status") == 200 and body:
            policy = RobotFileParser(ROBOTS_URL)
            policy.parse(body.decode("utf-8").splitlines())
            allowed = policy.can_fetch(USER_AGENT, EVENTS_URL)
        if allowed:
            calendar, body, _ = await fetch("events", "GET", EVENTS_URL, max_bytes=1_000_000)
            if calendar.get("http_status") == 200 and body:
                records = parse_calendar(body.decode("utf-8"))
        today = datetime.now(timezone.utc).date().isoformat()
        report["services"]["events"] = {"available": bool(records), "robots_permitted": allowed,
                                              "dated_records_parsed": len(records), "future_dated_records": sum(p.date >= today for p in records),
                                              "complete_city_calendar": False, "quota": "not_exposed"}

        item, body, _ = await fetch("valhalla", "POST", args.base_url + "/api/navigation/route",
                                          json={"coordinates": [[71.4304546, 51.1282882], [71.424, 51.12899]], "language": "ru"})
        route = json.loads(body) if item.get("http_status") == 200 and body else {}
        coordinates = route.get("geometry", {}).get("coordinates", [])
        report["services"]["valhalla"] = {"available": route.get("street_routed") is True and len(coordinates) > 2,
                                                 "http_status": item.get("http_status"), "provider": route.get("provider"),
                                                 "geometry_points": len(coordinates), "distance_m": route.get("distance_m"),
                                                 "step_count": sum(len(leg.get("steps", [])) for leg in route.get("legs", [])),
                                                 "quota": "anonymous_balance_not_exposed"}

        item, body, _ = await fetch("openfreemap", "GET", "https://tiles.openfreemap.org/styles/positron")
        style = json.loads(body) if item.get("http_status") == 200 and body else {}
        map_result = {"style_http_status": item.get("http_status"), "style_layers": len(style.get("layers", [])),
                      "tilejson_http_status": None, "tile_http_status": None, "available": False, "quota": "keyless_service_no_account_balance"}
        vector_url = next((s.get("url") for s in style.get("sources", {}).values() if s.get("type") == "vector"), None)
        if isinstance(vector_url, str) and trusted_map_url(vector_url):
            item, body, _ = await fetch("openfreemap", "GET", vector_url)
            tilejson = json.loads(body) if item.get("http_status") == 200 and body else {}
            map_result["tilejson_http_status"] = item.get("http_status")
            tiles = tilejson.get("tiles", [])
            if tiles and isinstance(tiles[0], str):
                zoom = 12
                tile_x = math.floor((CITY[1] + 180) / 360 * 2 ** zoom)
                tile_y = math.floor((1 - math.asinh(math.tan(math.radians(CITY[0]))) / math.pi) / 2 * 2 ** zoom)
                tile_url = tiles[0].replace("{z}", str(zoom)).replace("{x}", str(tile_x)).replace("{y}", str(tile_y))
                if trusted_map_url(tile_url):
                    tile, tile_body, _ = await fetch("openfreemap", "GET", tile_url)
                    map_result.update(tile_http_status=tile.get("http_status"), tile_bytes=len(tile_body or b""),
                                      available=tile.get("http_status") == 200 and bool(tile_body))
        report["services"]["openfreemap"] = map_result

    for service, names in {"google_places": ("GOOGLE_PLACES_API_KEY",), "yandex": ("YANDEX_MAPS_API_KEY", "YANDEX_API_KEY"),
                           "foursquare": ("FOURSQUARE_API_KEY",), "twilio": ("TWILIO_AUTH_TOKEN",)}.items():
        configured = any(os.getenv(name) for name in names)
        report["services"][service] = {"configured": configured, "live_checked": False,
                                           "status": "not_configured" if not configured else "not_probed", "quota": "unknown", "requests": 0}
    for name, path in {"alemplus": args.alemplus_report, "elevenlabs": args.elevenlabs_report}.items():
        external = receipt(path)
        report["external_receipts"][name] = {k: v for k, v in external.items() if k != "data"}
        if external.get("available"):
            data = external["data"]
            if name == "alemplus":
                report["services"][name] = {"available": data.get("passed", False), "services": data.get("services"),
                                                   "graph": data.get("graph"), "stt": data.get("stt"), "quota": "not_exposed_by_checked_endpoints",
                                                   "dataset_matches": data.get("dataset_sha256") == report["dataset_sha256"]}
            else:
                subscription = data.get("calls", {}).get("subscription", {})
                result = subscription.get("result", {})
                report["services"][name] = {"account_read_http_status": subscription.get("http_status"),
                                                    "character_limit": result.get("character_limit"), "characters_used": result.get("character_count"),
                                                    "characters_remaining": result.get("characters_remaining"), "can_extend": result.get("can_extend_character_limit"),
                                                    "quota_state": "near_exhausted" if result.get("characters_remaining", 0) < 500 else "available",
                                                    "new_generation_checked": False, "new_conversation_checked": False}
    report["counts"] = {"local_app_http_requests": sum(c["target"] == "local app" for c in report["calls"]),
                        "direct_provider_http_requests": sum(c["target"] == "provider" for c in report["calls"]),
                        "retries": 0, "tts_generations": 0, "voice_conversations": 0}
    report["limits"] = ["External receipts have their own timestamps and call budgets.",
                         "The local 2GIS and routing calls can trigger upstream provider requests; their provider payloads are discarded.",
                         "Dataset acquisition sources are imported provenance, not a claim that every upstream crawl is currently reachable.",
                         "No physical microphone or telephone call was tested."]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"report": str(args.output), "poi_count": report["poi_count"], "services": {
        name: {k: value[k] for k in ("available", "http_status", "status", "quota_state", "characters_remaining") if k in value}
        for name, value in report["services"].items()}, "counts": report["counts"]}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Authorize this bounded set of real external requests")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--alemplus-report", type=Path, default=ROOT / "artifacts/alemplus-readiness-2026-10-20.json")
    parser.add_argument("--elevenlabs-report", type=Path, default=ROOT / "artifacts/voice-languages-readonly-2026-10-20.json")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/api-readiness-2026-10-20.json")
    args = parser.parse_args()
    if not args.live:
        parser.error("Use --live to explicitly run the bounded readiness requests")
    asyncio.run(check(args))
