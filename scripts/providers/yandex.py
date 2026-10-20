"""Parse allowlisted metadata already delivered by a public Yandex organization card.

This module makes no network requests, executes no page scripts and does not
extract review bodies, authors, session data or image bytes. Observations remain
evaluation-only; public accessibility is not a redistribution licence.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit

HOSTS = {"yandex.com", "yandex.kz", "yandex.ru"}
ORG_PATH = re.compile(r"^/maps/org/(?:[^/]+/)?(\d+)/?(?:reviews/|gallery/)?$")


def organization_id(url: str) -> str | None:
    """Accept public organization links only; drop credentials and query tokens."""
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.username or parsed.password:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if port not in {None, 443}:
        return None
    match = ORG_PATH.fullmatch(parsed.path)
    return match[1] if match else None


class _PublicState(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: list[dict] = []
        self._capturing = False
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = dict(attrs)
        if tag == "script":
            self._capturing = (
                (data.get("type") or "").split(";", 1)[0].strip().lower() == "application/json"
                and "state-view" in (data.get("class") or "").split()
            )
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._capturing:
            self._capturing = False
            try:
                value = json.loads("".join(self._parts))
                if isinstance(value, dict):
                    self.values.append(value)
            except (ValueError, RecursionError):
                pass
            self._parts = []


def _businesses(value: object, depth: int = 0):
    if depth > 40:
        return
    if isinstance(value, dict):
        if value.get("type") == "business":
            yield value
            return  # Do not traverse its related organizations or user reviews.
        for child in value.values():
            yield from _businesses(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            yield from _businesses(child, depth + 1)


def _number(value: object, minimum: float, maximum: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and minimum <= value <= maximum else None


def _count(value: object) -> int | None:
    number = _number(value, 0, 1_000_000_000)
    return int(number) if number is not None and number.is_integer() else None


def _photo_link(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if (parsed.scheme != "https" or parsed.hostname != "avatars.mds.yandex.net"
            or parsed.username or parsed.password or port not in {None, 443}
            or not parsed.path.startswith("/get-altay/") or parsed.query or parsed.fragment):
        return None
    return value.replace("%s", "orig") if "%s" in value else value


def parse_html(html: str, url: str, *, observed_at: str | None = None) -> list[dict]:
    """Return only the exact organization identified by the requested public URL.

    City/map viewport coordinates and nearby organizations are deliberately
    ignored. The returned image URLs are source references, never permission to
    download, cache, train on or redistribute those images.
    Supply the original acquisition time; cached parsing never establishes it.
    """
    provider_id = organization_id(url)
    if provider_id is None or len(html) > 2_500_000:
        return []
    parser = _PublicState()
    try:
        parser.feed(html)
    except (ValueError, RecursionError):
        return []
    business = next((item for state in parser.values for item in _businesses(state)
                     if str(item.get("id", "")) == provider_id
                     and item.get("uri") == "ymapsbm1://org?oid=" + provider_id), None)
    if business is None or not isinstance(business.get("title"), str) or not business["title"].strip():
        return []

    coordinates = business.get("coordinates")
    lon = lat = None
    if isinstance(coordinates, list) and len(coordinates) == 2:
        lon, lat = _number(coordinates[0], -180, 180), _number(coordinates[1], -90, 90)
        if lon is None or lat is None:
            lon = lat = None
    ratings = business.get("ratingData") if isinstance(business.get("ratingData"), dict) else {}
    photos = business.get("photos") if isinstance(business.get("photos"), dict) else {}
    photo_items = photos.get("items") if isinstance(photos.get("items"), list) else []
    links = list(dict.fromkeys(link for item in photo_items[:20] if isinstance(item, dict)
                               if (link := _photo_link(item.get("urlTemplate")))))
    parsed = urlsplit(url)
    source_path = re.sub(r"/(?:reviews|gallery)/?$", "/", parsed.path)
    source_url = urlunsplit(("https", parsed.hostname, source_path, "", ""))
    warnings = ["Provider metadata is evaluation-only; no redistribution licence verified.",
                "Photo source links are not licensed image assets; review bodies were not collected."]
    if not isinstance(observed_at, str) or not observed_at.strip():
        observed_at = None
        warnings.append("Original acquisition time is unknown; parsing cached content does not establish freshness.")
    if lat is None:
        warnings.append("Exact organization coordinates were not available.")
    elif not (50.95 <= lat <= 51.40 and 71.10 <= lon <= 71.85):
        warnings.append("Organization coordinates fall outside the Astana research bounds.")
    return [{
        "provider": "yandex", "provider_id": provider_id, "source_url": source_url,
        "name": business["title"].strip()[:500], "lat": lat, "lon": lon,
        "address": business.get("address") if isinstance(business.get("address"), str) else None,
        "rating": _number(ratings.get("ratingValue"), 1, 5), "rating_scale": 5,
        "rating_count": _count(ratings.get("ratingCount")), "review_count": _count(ratings.get("reviewCount")),
        "photo_source_links": links, "review_source_links": [source_url.rstrip("/") + "/reviews/"],
        "observed_at": observed_at, "access_method": "http",
        "http_status": None, "evidence_sha256": hashlib.sha256(html.encode()).hexdigest(),
        "matched_poi_ids": [], "identity_evidence": ["Exact numeric organization ID matches public URL and public state URI."],
        "import_policy": "evaluation_only", "warnings": warnings,
    }]
