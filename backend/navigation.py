"""Bounded, transient pedestrian routing against the Valhalla street graph.

Provider failures are surfaced: a straight line is never sold as navigation.
Only the configured server is called; neither client URLs nor user text reach it.
"""
from __future__ import annotations

import asyncio
import copy
import math
import os
import re
import time
from collections import OrderedDict
from typing import Literal
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_ROUTER_URL = "https://valhalla1.openstreetmap.de"
# Includes Astana's central neighbourhoods and airport, never arbitrary countries.
ASTANA_BOUNDS = (71.15, 50.95, 71.75, 51.35)
MAX_RESPONSE_BYTES = 2_000_000
MAX_POINTS = 40_000
LANGUAGES = {"en": "en-US", "ru": "ru-RU", "kk": "en-US"}


class NavigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    coordinates: list[tuple[float, float]] = Field(min_length=2, max_length=4)
    language: Literal["en", "ru", "kk"] = "en"

    @field_validator("coordinates", mode="before")
    @classmethod
    def validate_coordinates(cls, value):
        if not isinstance(value, list):
            raise ValueError("Provide an ordered list of longitude, latitude pairs")
        if not 2 <= len(value) <= 4:
            raise ValueError("Provide between two and four route stops")
        west, south, east, north = ASTANA_BOUNDS
        for pair in value:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise ValueError("Coordinates must be [longitude, latitude] pairs")
            if any(type(v) not in (int, float) or (type(v) is float and not math.isfinite(v)) for v in pair):
                raise ValueError("Coordinates must be finite numbers")
            lon, lat = pair
            if not west <= lon <= east or not south <= lat <= north:
                raise ValueError("Walking navigation is available within Astana only")
        if any(first == second for first, second in zip(value, value[1:])):
            raise ValueError("Consecutive route stops must be different locations")
        return value


def _provider_url() -> str:
    base = os.getenv("QALA_VALHALLA_URL", DEFAULT_ROUTER_URL).rstrip("/")
    parsed = urlsplit(base)
    # Accessing port also validates malformed operator configuration up front.
    _ = parsed.port
    # HTTP is supported solely for an operator's local self-hosted service.
    local_http = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
            or not (parsed.scheme == "https" or local_http)):
        raise ValueError("QALA_VALHALLA_URL must be HTTPS, or HTTP on a loopback host")
    return base + "/route"


def _number(value, maximum: float) -> float:
    if type(value) not in (int, float) or not 0 <= value <= maximum or not math.isfinite(value):
        raise ValueError("Invalid provider measurement")
    return float(value)


def _object(value) -> dict:
    if not isinstance(value, dict):
        raise ValueError("Invalid provider object")
    return value


def _point(lon: float, lat: float) -> list[float]:
    # Permit a small detour outside the request area, but reject corrupt shapes.
    west, south, east, north = ASTANA_BOUNDS
    if not west - .1 <= lon <= east + .1 or not south - .1 <= lat <= north + .1:
        raise ValueError("Provider returned geometry outside Astana")
    return [lon, lat]


def decode_polyline6(encoded: str) -> list[list[float]]:
    """Valhalla's documented native shape is a 6-decimal encoded polyline."""
    if not isinstance(encoded, str) or not 2 <= len(encoded) <= 500_000:
        raise ValueError("Invalid provider shape")
    index, latitude, longitude = 0, 0, 0
    points = []
    while index < len(encoded):
        deltas = []
        for _ in range(2):
            result, shift = 0, 0
            while True:
                if index >= len(encoded) or shift > 35:
                    raise ValueError("Malformed provider polyline")
                chunk = ord(encoded[index]) - 63
                index += 1
                if not 0 <= chunk <= 63:
                    raise ValueError("Malformed provider polyline")
                result |= (chunk & 31) << shift
                shift += 5
                if chunk < 32:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        latitude += deltas[0]
        longitude += deltas[1]
        points.append(_point(longitude / 1_000_000, latitude / 1_000_000))
        if len(points) > MAX_POINTS:
            raise ValueError("Provider shape exceeds route limit")
    if len(points) < 2:
        raise ValueError("Provider returned an empty route")
    return points


def _distance(first, second) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (*first, *second))
    a = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6_371_000 * 2 * math.asin(min(1, math.sqrt(a)))


def normalize_route(data: dict, request: NavigationRequest) -> dict:
    """Trust neither HTTP 200 nor provider geometry/indices without validation."""
    trip = _object(_object(data)["trip"])
    if type(trip.get("status")) is not int or trip["status"] != 0 or trip.get("units") != "kilometers":
        raise ValueError("Provider did not return a successful metric route")
    raw_legs = trip["legs"]
    if not isinstance(raw_legs, list) or len(raw_legs) != len(request.coordinates) - 1:
        raise ValueError("Provider returned an unexpected number of legs")
    geometry, legs, waypoints = [], [], []
    for leg_index, raw in enumerate(raw_legs):
        raw = _object(raw)
        points = decode_polyline6(raw["shape"])
        if geometry and _distance(geometry[-1], points[0]) > 10:
            raise ValueError("Provider route legs are disconnected")
        offset = len(geometry) - (1 if geometry else 0)
        geometry.extend(points[1:] if geometry else points)
        if len(geometry) > MAX_POINTS:
            raise ValueError("Provider shape exceeds route limit")
        summary = _object(raw["summary"])
        distance_m = _number(summary["length"], 100) * 1000
        duration_seconds = _number(summary["time"], 86_400)
        raw_steps = raw["maneuvers"]
        if not isinstance(raw_steps, list) or not 1 <= len(raw_steps) <= 500:
            raise ValueError("Provider did not return walking instructions")
        steps = []
        for maneuver in raw_steps:
            maneuver = _object(maneuver)
            begin, end = maneuver["begin_shape_index"], maneuver["end_shape_index"]
            if type(begin) is not int or type(end) is not int or not 0 <= begin <= end < len(points):
                raise ValueError("Provider maneuver points are invalid")
            if maneuver.get("travel_mode") != "pedestrian":
                raise ValueError("Provider returned a non-walking segment")
            instruction = maneuver["instruction"]
            if not isinstance(instruction, str) or len(instruction) > 1500:
                raise ValueError("Provider instruction is missing or too long")
            instruction = re.sub(r"[\x00-\x1f\x7f]", " ", instruction).strip()
            if not instruction:
                raise ValueError("Provider instruction is empty")
            maneuver_type = maneuver["type"]
            if type(maneuver_type) is not int or not 0 <= maneuver_type <= 100:
                raise ValueError("Provider maneuver type is invalid")
            steps.append({
                "instruction": instruction,
                "distance_m": round(_number(maneuver["length"], 100) * 1000, 1),
                "duration_seconds": round(_number(maneuver["time"], 86_400), 1),
                "location": points[begin], "maneuver_type": maneuver_type,
                "geometry_start_index": offset + begin, "geometry_end_index": offset + end,
            })
        legs.append({"distance_m": round(distance_m, 1), "duration_seconds": round(duration_seconds, 1), "steps": steps})
        # Make unavoidable snapping to an OSM path visible; never imply that a
        # POI's area centre is an inspected public entrance.
        if not leg_index:
            waypoints.append({"input": list(request.coordinates[0]), "routed": points[0]})
        waypoints.append({"input": list(request.coordinates[leg_index + 1]), "routed": points[-1]})
    for waypoint in waypoints:
        waypoint["snap_distance_m"] = round(_distance(waypoint["input"], waypoint["routed"]), 1)
        if waypoint["snap_distance_m"] > 1000:
            raise ValueError("Provider snapped too far from a requested stop")
    summary = _object(trip["summary"])
    distance_m = round(_number(summary["length"], 100) * 1000, 1)
    duration_seconds = round(_number(summary["time"], 86_400), 1)
    if (abs(sum(leg["distance_m"] for leg in legs) - distance_m) > max(10, distance_m * .01)
            or abs(sum(leg["duration_seconds"] for leg in legs) - duration_seconds) > 10):
        raise ValueError("Provider trip and leg summaries disagree")
    language_used = {"en-US": "en", "ru-RU": "ru"}.get(trip.get("language"))
    if language_used is None or trip["language"] != LANGUAGES[request.language]:
        raise ValueError("Provider returned an unexpected narrative language")
    lons, lats = zip(*geometry)
    return {
        "geometry": {"type": "LineString", "coordinates": geometry},
        "distance_m": distance_m, "duration_seconds": duration_seconds, "legs": legs,
        "bounds": [min(lons), min(lats), max(lons), max(lats)], "waypoints": waypoints,
        "provider": "Valhalla", "attribution": "Routing: Valhalla · Map data © OpenStreetMap contributors",
        "attribution_url": "https://www.openstreetmap.org/copyright",
        "mode": "walking", "street_routed": True,
        "language_requested": request.language, "language_used": language_used,
        "language_fallback": request.language != language_used,
        "warnings": (["Kazakh turn instructions are unavailable; directions are in English."] if request.language == "kk" else [])
            + (["One or more places are over 75 m from the mapped path. Confirm the public entrance on arrival."]
               if any(point["snap_distance_m"] > 75 for point in waypoints) else []),
        "limitations": "OSM pedestrian route; timings are estimates. Entrances, temporary closures and step-free access are not verified.",
    }


class WalkingRouter:
    """Small bounded in-memory cache reduces public demo-server traffic.

    Routes (including precise geometry) expire after five minutes and are never
    persisted. The UI explicitly starts navigation; only coordinates/language
    are sent, never messages, memory identifiers or saved preferences.
    """
    def __init__(self):
        self.url = _provider_url()
        self.cache: OrderedDict[tuple, tuple[float, dict]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def route(self, request: NavigationRequest) -> dict:
        key = (tuple(request.coordinates), request.language)
        # Serialize misses to respect the public server and coalesce identical
        # concurrent requests. Cache hits do not touch the network.
        async with self._lock:
            now = time.monotonic()
            for old in list(self.cache):
                if self.cache[old][0] <= now:
                    del self.cache[old]
            if key in self.cache:
                self.cache.move_to_end(key)
                return copy.deepcopy(self.cache[key][1])
            payload = {
                "locations": [{"lon": lon, "lat": lat, "type": "break", "search_cutoff": 1000}
                              for lon, lat in request.coordinates],
                "costing": "pedestrian", "costing_options": {"pedestrian": {"max_distance": 50_000}},
                "units": "kilometers", "language": LANGUAGES[request.language], "directions_type": "instructions",
            }
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(18, connect=5), follow_redirects=False) as client:
                    async with client.stream("POST", self.url, json=payload, headers={
                        "X-Client-Id": os.getenv("QALA_ROUTING_CLIENT_ID", "qala-astana-local-demo"),
                        "Accept": "application/json", "User-Agent": "Qala-Astana/1.0 (walking-demo)",
                    }) as response:
                        if response.status_code == 429:
                            raise HTTPException(503, "Walking router is busy. Try again shortly.", headers={"Retry-After": "60"})
                        if response.status_code == 400:
                            raise HTTPException(422, "No walking route could be found between these stops. Choose another place.")
                        if response.status_code != 200:
                            raise HTTPException(503, "Walking router is unavailable. Your places are still available; try navigation again shortly.")
                        content = bytearray()
                        async for chunk in response.aiter_bytes():
                            content.extend(chunk)
                            if len(content) > MAX_RESPONSE_BYTES:
                                raise ValueError("Provider response exceeds route limit")
                data = httpx.Response(200, content=bytes(content)).json()
                result = normalize_route(data, request)
            except httpx.HTTPError as exc:
                raise HTTPException(503, "Walking router could not be reached. Please try navigation again shortly.") from exc
            except (ValueError, KeyError, TypeError, IndexError, OverflowError) as exc:
                raise HTTPException(502, "Walking router returned an invalid route. Please try another destination.") from exc
            self.cache[key] = (time.monotonic() + 300, result)
            while len(self.cache) > 64:
                self.cache.popitem(last=False)
            return copy.deepcopy(result)
