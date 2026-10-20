"""On-demand owned-key 2GIS profiles, separate from the reusable POI corpus.

Only a user's explicit source lookup issues a request. Completed responses are
not cached; simultaneous callers share an in-flight request.
Content never enters the dataset, RAG index or preference memory. Credentials
and upstream exception/body text never enter responses.
"""
from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timezone
import ipaddress
import json
import logging
import math
import os
import re
import time
import unicodedata
from urllib.parse import urlsplit

import httpx


ORIGIN = "https://catalog.api.2gis.com"
LOCALES = {"ru": "ru_KZ", "kk": "kk_KZ", "en": "en_RU"}
FIELDS = ",".join("items." + field for field in (
    "point", "reviews", "schedule", "schedule_special", "contact_groups",
    "rubrics", "flags", "full_address_name", "name_ex"))
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
CROSSWALK = {
    "osm-node-4894937300": {
        "provider_id": "70000001018608940", "name": "National Museum of the Republic of Kazakhstan",
        "lat": 51.1182297, "lon": 71.4693823,
        "source_url": "https://www.openstreetmap.org/node/4894937300",
    },
    "osm-way-230401645": {
        "provider_id": "70000001021365759", "name": "Bayterek",
        "lat": 51.1282882, "lon": 71.4304546,
        "source_url": "https://www.openstreetmap.org/way/230401645",
    },
}


class _CredentialLogFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple):
            record.args = tuple(value.copy_set_param("key", "[redacted]")
                                if isinstance(value, httpx.URL) and value.host == "catalog.api.2gis.com" and "key" in value.params
                                else value for value in record.args)
        return True


# httpx INFO logs contain request URLs. The provider puts its key in the query,
# so redact that typed URL before any configured application handler sees it.
logging.getLogger("httpx").addFilter(_CredentialLogFilter())


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _number(value, minimum, maximum):
    return value if type(value) in {int, float} and math.isfinite(value) and minimum <= value <= maximum else None


def _count(value):
    return value if type(value) is int and 0 <= value <= 100_000_000 else None


def _name(value: str) -> str:
    text = "".join(character for character in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(character))
    return re.sub(r"\bмузеи рк\b", "музеи республики казахстан", " ".join(re.findall(r"[^\W_]+", text)))


def _aliases(poi: dict) -> set[str]:
    names = [poi.get("name")]
    names.extend(poi.get("names", {}).values() if isinstance(poi.get("names"), dict) else [])
    names.extend(poi.get("aliases", []) if isinstance(poi.get("aliases"), list) else [])
    tags = poi.get("raw_tags", {})
    if isinstance(tags, dict):
        names.extend(value for key, value in tags.items() if isinstance(key, str) and (key == "name" or key.startswith(("name:", "alt_name", "official_name", "short_name"))))
    return {_name(part) for value in names if isinstance(value, str) for part in value.split(";") if part.strip()}


def _distance(lat, lon, other_lat, other_lon):
    a, b = math.radians(lat), math.radians(other_lat)
    half = math.sin((b - a) / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(math.radians(other_lon - lon) / 2) ** 2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(half)))


def _point(value):
    if not isinstance(value, dict):
        return None
    lat, lon = _number(value.get("lat"), -90, 90), _number(value.get("lon"), -180, 180)
    return (lat, lon) if lat is not None and lon is not None else None


def _known_id(poi: dict) -> str | None:
    known = CROSSWALK.get(poi.get("id"))
    if not known:
        return None
    point = _point(poi)
    if (point is None or _name(known["name"]) not in _aliases(poi)
            or not isinstance(poi.get("source"), dict) or poi["source"].get("url") != known["source_url"]
            or _distance(*point, known["lat"], known["lon"]) > 200):
        return None
    return known["provider_id"]


class TwoGIS:
    def __init__(self, *, key: str | None = None, transport=None, clock=time.monotonic,
                 sleep=asyncio.sleep, request_budget: int = 80):
        self._key = (os.getenv("TWOGIS_API_KEY", "") if key is None else key).strip()
        self._clock, self._sleep = clock, sleep
        self._budget = max(0, min(80, request_budget))
        self._requests = 0
        self._last_start: float | None = None
        self._verified = False
        self._checked_at: str | None = None
        self._error: str | None = None
        self._blocked = False
        self._lock = asyncio.Lock()
        self._flight_lock = asyncio.Lock()
        self._inflight: dict[tuple, asyncio.Task] = {}
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(8, connect=3), follow_redirects=False,
                                         trust_env=False, transport=transport,
                                         headers={"User-Agent": "Qala/1.0 (explicit place source lookup)"})

    async def close(self):
        for task in self._inflight.values():
            task.cancel()
        await asyncio.gather(*self._inflight.values(), return_exceptions=True)
        self._inflight.clear()
        await self._client.aclose()

    def status(self) -> dict:
        return {"configured": bool(self._key), "live_verified": self._verified,
                "checked_at": self._checked_at, "error_code": self._error,
                "budget_remaining": max(0, self._budget - self._requests)}

    def _text(self, value, maximum=500):
        if not isinstance(value, str) or self._key and self._key in value:
            return None
        text = " ".join(value.split())[:maximum]
        return text or None

    def _url(self, value):
        value = self._text(value, 1500)
        if not value:
            return None
        try:
            parts = urlsplit(value)
            host = (parts.hostname or "").rstrip(".").casefold()
            if parts.scheme not in {"https", "http"} or not host or parts.username or parts.password or parts.port not in {None, 80, 443}:
                return None
            if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
                return None
            try:
                if not ipaddress.ip_address(host).is_global:
                    return None
            except ValueError:
                pass
            if re.search(r"(?:^|[?&])(?:key|api_key|token|signature|authorization|access_token)=", parts.query, re.I):
                return None
        except ValueError:
            return None
        return value

    def _intervals(self, value):
        if not isinstance(value, list):
            return []
        result = []
        for item in value[:12]:
            if not isinstance(item, dict):
                continue
            values = (item.get("from"), item.get("to"))
            if all(isinstance(value, str) and re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]|24:00", value) for value in values):
                result.append({"from": values[0], "to": values[1]})
        return result

    def _schedule(self, value):
        result = {}
        if isinstance(value, dict):
            for day in DAYS:
                if isinstance(value.get(day), dict):
                    result[day] = {"working_hours": self._intervals(value[day].get("working_hours"))}
        return result

    def _special(self, value, depth=0):
        if depth > 4:
            return None
        if value is None or type(value) is bool:
            return value
        if isinstance(value, str):
            return self._text(value, 800)
        if isinstance(value, list):
            return [self._special(item, depth + 1) for item in value[:20]]
        if isinstance(value, dict):
            allowed = {*DAYS, "working_hours", "from", "to", "comment", "date", "date_from", "date_to",
                       "start_date", "end_date", "is_closed", "is_24x7", "dates", "type"}
            result = {key: self._special(item, depth + 1) for key, item in value.items() if key in allowed}
            return result or None
        return None

    def _source(self, item: dict) -> dict | None:
        identifier, point = item.get("id"), _point(item.get("point"))
        name = self._text(item.get("name"), 300)
        if not isinstance(identifier, str) or not re.fullmatch(r"[0-9]{8,20}", identifier) or not point or not name:
            return None
        url = "https://2gis.kz/astana/firm/" + identifier
        reviews = item.get("reviews") if isinstance(item.get("reviews"), dict) else {}
        native = {}
        for field in ("general_rating", "general_review_count", "general_review_count_with_stars", "org_rating", "org_review_count", "org_review_count_with_stars"):
            value = _number(reviews.get(field), 0, 5) if field.endswith("rating") else _count(reviews.get(field))
            if value is not None:
                native[field] = value
        contacts = []
        for group in item.get("contact_groups", []) if isinstance(item.get("contact_groups"), list) else []:
            if not isinstance(group, dict):
                continue
            for contact in group.get("contacts", [])[:12] if isinstance(group.get("contacts"), list) else []:
                if not isinstance(contact, dict):
                    continue
                kind = self._text(contact.get("type"), 50)
                value = self._text(contact.get("value") or contact.get("text"), 500)
                if kind and value and len(contacts) < 20:
                    contacts.append({"type": kind, "value": value, "url": self._url(contact.get("url")),
                                     "comment": self._text(contact.get("comment") or group.get("comment"), 300)})
        rubrics = []
        for rubric in item.get("rubrics", [])[:12] if isinstance(item.get("rubrics"), list) else []:
            if isinstance(rubric, dict) and self._text(rubric.get("name"), 200):
                rubrics.append({"id": self._text(rubric.get("id"), 50) or "", "name": self._text(rubric["name"], 200)})
        schedule = item.get("schedule") if isinstance(item.get("schedule"), dict) else {}
        flags = item.get("flags") if isinstance(item.get("flags"), dict) else {}
        return {"provider": "2gis", "provider_id": identifier, "name": name, "url": url,
                "lat": point[0], "lon": point[1],
                "address": self._text(item.get("full_address_name") or item.get("address_name"), 500),
                "rating": native.get("general_rating"), "rating_count": native.get("general_review_count_with_stars"),
                "review_count": native.get("general_review_count"), "native_statistics": native,
                "schedule": self._schedule(schedule), "schedule_special": self._special(item.get("schedule_special")),
                "schedule_comment": self._text(schedule.get("comment"), 800),
                "contacts": contacts, "rubrics": rubrics,
                "photo_gallery_url": url + "/tab/photos", "review_url": url + "/tab/reviews",
                "has_photos": flags.get("photos") if type(flags.get("photos")) is bool else None,
                "route_url": None}

    async def _request(self, path: str, params: dict) -> dict | None:
        if self._blocked or self._requests >= self._budget:
            self._verified = False
            self._error = "access_paused" if self._blocked else "request_budget_exhausted"
            return None
        if self._last_start is not None:
            wait = self._last_start + 1 - self._clock()
            if wait > 0:
                await self._sleep(wait)
        self._last_start = self._clock()
        self._requests += 1
        self._checked_at = _stamp()
        try:
            async with asyncio.timeout(10):
                async with self._client.stream("GET", ORIGIN + path, params={**params, "key": self._key, "fields": FIELDS}) as response:
                    if response.status_code != 200:
                        self._blocked = response.status_code in {401, 403, 429}
                        raise ValueError("Upstream status rejected")
                    parts, total = [], 0
                    async for part in response.aiter_bytes():
                        total += len(part)
                        if total > 1_000_000:
                            raise ValueError("Response too large")
                        parts.append(part)
            payload = json.loads(b"".join(parts))
            meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
            code = meta.get("code") if isinstance(meta, dict) else None
            if type(code) is not int or code != 200:
                self._blocked = code in {401, 403, 429}
                raise ValueError("Provider meta code rejected")
            result = payload.get("result")
            items = result.get("items") if isinstance(result, dict) else None
            if not isinstance(items, list) or any(not isinstance(item, dict) for item in items) or len(items) > 20:
                raise ValueError("Invalid provider result")
            total = result.get("total")
            if total is not None and (_count(total) is None or total < len(items)):
                raise ValueError("Invalid provider result total")
            self._verified, self._error = True, None
            return {"items": items[:5], "total": total,
                    "truncated": len(items) > 5 or total is not None and total > len(items),
                    "completeness_unknown": total is None and len(items) >= 5}
        except (httpx.HTTPError, ValueError, TypeError, UnicodeError, TimeoutError):
            self._verified, self._error = False, "provider_unavailable"
            return None

    async def lookup(self, poi: dict, language: str = "ru") -> dict:
        if language not in LOCALES:
            raise ValueError("Unsupported source language")
        base = {"status": "not_found", "checked_at": _stamp(), "cached": False, "reason": None,
                "source": None, "candidates": []}
        if str(poi.get("operating_status", "")).strip().casefold() == "closed":
            return {**base, "reason": "local_closed"}
        point, aliases = _point(poi), _aliases(poi)
        if point is None or not aliases or poi.get("name_derived") is True:
            return {**base, "reason": "local_identity_missing"}
        if not self._key:
            return {**base, "status": "key_required", "reason": "key_required"}
        cache_key = (poi.get("id"), language, *point, tuple(sorted(aliases)))
        async with self._flight_lock:
            task = self._inflight.get(cache_key)
            coalesced = task is not None and not task.done()
            if task is None or task.done():
                task = asyncio.create_task(self._lookup(poi, language, base, point, aliases))
                self._inflight[cache_key] = task
                def completed(finished):
                    if self._inflight.get(cache_key) is finished:
                        self._inflight.pop(cache_key, None)
                task.add_done_callback(completed)
        result = copy.deepcopy(await asyncio.shield(task))
        result["coalesced"] = coalesced
        return result

    async def _lookup(self, poi, language, base, point, aliases):
        async with self._lock:
            known = _known_id(poi)
            params = {"locale": LOCALES[language]}
            if known:
                path, params["id"] = "/3.0/items/byid", known
            else:
                path = "/3.0/items"
                name = poi.get("names", {}).get(language) if isinstance(poi.get("names"), dict) else None
                name = name if isinstance(name, str) and name.strip() else poi.get("name", "")
                address = poi.get("address") if isinstance(poi.get("address"), str) else ""
                params.update(q=(str(name) + " " + address).strip()[:400], point=f"{point[1]},{point[0]}", radius=200, type="branch", page_size=5)
            provider_result = await self._request(path, params)
            response = {**base, "checked_at": self._checked_at or _stamp()}
            if provider_result is None:
                response.update(status="unavailable", reason=self._error)
                return response
            candidates, matches, unknown_coordinates = [], [], False
            for item in provider_result["items"]:
                provider_names = set()
                name = self._text(item.get("name"), 300)
                if name:
                    provider_names.add(_name(name))
                name_ex = item.get("name_ex")
                if isinstance(name_ex, dict) and self._text(name_ex.get("primary"), 300):
                    provider_names.add(_name(name_ex["primary"]))
                if not known and provider_names & aliases and _point(item.get("point")) is None:
                    unknown_coordinates = True
                source = self._source(item)
                if source is None:
                    continue
                delta = _distance(*point, source["lat"], source["lon"])
                candidates.append({key: source[key] for key in ("provider_id", "name", "url", "lat", "lon", "address")})
                candidates[-1]["distance_m"] = round(delta, 1)
                if delta <= 200 and (source["provider_id"] == known if known else bool(provider_names & aliases)):
                    matches.append(source)
            uncertain = None
            if not known:
                if unknown_coordinates:
                    uncertain = "candidate_coordinates_missing"
                elif provider_result["truncated"]:
                    uncertain = "result_truncated"
                elif provider_result["completeness_unknown"]:
                    uncertain = "result_completeness_unknown"
            if uncertain:
                response.update(status="ambiguous" if candidates else "not_found", candidates=candidates, reason=uncertain)
            elif len(matches) == 1:
                response.update(status="matched", source=matches[0])
            elif candidates:
                response.update(status="ambiguous", candidates=candidates, reason="identity_not_unique" if len(matches) > 1 else "identity_not_verified")
            else:
                response["reason"] = "no_provider_match"
            return response
