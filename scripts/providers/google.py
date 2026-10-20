"""Parse explicit, public Google card metadata for a bounded source audit.

This module does not call private Maps endpoints, decode initialization arrays,
download photos, or publish Google content into the reusable POI catalogue.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit


PROVIDER = "google"


def _number(value: Any, *, integer: bool = False) -> int | float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(str(value).replace("\u00a0", "").replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result) or result < 0 or (integer and not result.is_integer()):
        return None
    return int(result) if integer else result


def _safe_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        return None
    return value


def _identity(url: str) -> tuple[str | None, float | None, float | None, str]:
    """Use only IDs and coordinates explicitly present in the public URL."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host not in {"www.google.com", "maps.google.com", "google.com"}:
        raise ValueError("A first-party Google Maps URL is required")
    decoded = unquote(parts.path)
    query = parse_qs(parts.query)
    entity = re.search(r"!1s(0x[0-9a-f]+:0x[0-9a-f]+|ChI[A-Za-z0-9_-]+)", decoded, re.I)
    provider_id = entity.group(1) if entity else (query.get("query_place_id") or query.get("cid") or [None])[0]
    coords = re.search(r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)", decoded)
    # The viewport after /@ is not a place coordinate and must not be used.
    lat, lon = (float(coords.group(1)), float(coords.group(2))) if coords else (None, None)
    if lat is not None and (not -90 <= lat <= 90 or not -180 <= lon <= 180):
        lat, lon = None, None
    canonical = urlunsplit(("https", "www.google.com", parts.path, "", ""))
    if not decoded.startswith("/maps/place/"):
        canonical = url
    return provider_id, lat, lon, canonical


def parse_visible_card(card: dict[str, Any], url: str | None = None, *, observed_at: str | None = None) -> dict[str, Any]:
    """Parse DOM evidence whose rating header is scoped to the selected place.

    Nested businesses and review text are deliberately excluded. The browser
    capture must provide ``header_text`` and ``rating_labels`` from the sibling
    immediately following the primary H1, not from the entire Maps sidebar.
    Acquisition time must come from the capture or an explicit original value.
    """
    url = url or str(card.get("url", ""))
    provider_id, lat, lon, canonical = _identity(url)
    name = card.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("The selected Google place H1 is missing")
    header_text = str(card.get("header_text") or "")
    rating = _number(card.get("rating"))
    if rating is None:
        # The first standalone 0..5 value in the primary place header is the
        # aggregate. Never scan body text containing nearby businesses.
        match = re.search(r"(?:^|\n)\s*([0-5](?:[.,]\d)?)\s*(?:\n|$)", header_text)
        rating = _number(match.group(1)) if match else None
    if rating is not None and not 0 <= rating <= 5:
        rating = None
    count = _number(card.get("rating_count"), integer=True)
    review_count = _number(card.get("review_count"), integer=True)
    warnings = [
        "Public card observations are evaluation evidence, not a dataset redistribution licence.",
        "Visible photos were not downloaded; author/licence metadata must be obtained through an authorized workflow.",
    ]
    if card.get("limited_version"):
        warnings.append("Google served its explicitly labelled limited Maps version.")
    if re.search(r"permanently closed|закрыт[оа]? навсегда|больше не работает|мүлдем жабық", header_text, re.I):
        warnings.append("Primary Google place header says permanently closed; verify with the operator before recommending this place.")
    if count is None:
        warnings.append("Primary aggregate rating count was not visible; nested business counts are excluded.")
    links: list[str] = []
    for image in card.get("primary_photo_links", []):
        link = _safe_url(image)
        if link and link not in links:
            links.append(link)
    observed = observed_at if observed_at is not None else card.get("observed_at")
    if not isinstance(observed, str) or not observed.strip():
        observed = None
        warnings.append("Original acquisition time is unknown; parsing cached content does not establish freshness.")
    evidence = json.dumps(card, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return {
        "provider": PROVIDER,
        "provider_id": provider_id,
        "source_url": canonical,
        "name": name.strip(),
        "lat": lat,
        "lon": lon,
        "address": card.get("address") or None,
        "rating": rating,
        "rating_scale": 5,
        "rating_count": count,
        "review_count": review_count,
        "photo_source_links": links[:1],
        "review_source_links": [],
        "observed_at": observed,
        "access_method": "browser",
        "http_status": card.get("http_status"),
        "evidence_sha256": hashlib.sha256(evidence).hexdigest(),
        "matched_poi_ids": [],
        "identity_evidence": ["Name from the selected place H1", "Coordinates and entity ID from public canonical place URL"] if lat is not None else ["Name from the selected place H1"],
        "import_policy": "evaluation_only",
        "warnings": warnings,
    }


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.jsonld: list[str] = []
        self._json = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        fields = dict(attrs)
        if tag == "meta":
            key = fields.get("property") or fields.get("name")
            if key and fields.get("content"):
                self.meta[key] = str(fields["content"])
        elif tag == "script" and fields.get("type") == "application/ld+json":
            self._json = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._json = False

    def handle_data(self, value: str) -> None:
        if self._json:
            self.jsonld.append(value)


def parse_html(html: str, url: str, *, observed_at: str | None = None) -> list[dict[str, Any]]:
    """Extract only public semantic metadata, never private initialization data.

    Generic Maps bootstraps return no rows. The current live ordinary HTTP
    probes do not expose stable place-specific JSON-LD; the browser audit is
    kept separate rather than manufacturing an HTTP-parser success.
    Cached metadata without original acquisition time remains explicitly dated
    unknown, rather than receiving the time at which it is parsed.
    """
    _identity(url)
    parser = _MetadataParser()
    parser.feed(html)
    rows: list[dict[str, Any]] = []
    for raw in parser.jsonld:
        try:
            value = json.loads(raw)
        except (ValueError, TypeError):
            continue
        entities = value if isinstance(value, list) else value.get("@graph", [value]) if isinstance(value, dict) else []
        for item in entities:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                continue
            kind = item.get("@type", [])
            kinds = [kind] if isinstance(kind, str) else kind
            if not isinstance(kinds, list) or not set(kinds).intersection({"Place", "LocalBusiness", "Museum", "TouristAttraction", "CafeOrCoffeeShop", "Restaurant", "ShoppingCenter"}):
                continue
            aggregate = item.get("aggregateRating", {})
            aggregate = aggregate if isinstance(aggregate, dict) else {}
            image = item.get("image")
            images = image if isinstance(image, list) else [image] if isinstance(image, str) else []
            row = parse_visible_card({"name": item["name"], "rating": aggregate.get("ratingValue"), "rating_count": aggregate.get("ratingCount"), "review_count": aggregate.get("reviewCount"), "primary_photo_links": images}, url, observed_at=observed_at)
            row["access_method"] = "http"
            row["evidence_sha256"] = hashlib.sha256(html.encode()).hexdigest()
            rows.append(row)
    return rows
