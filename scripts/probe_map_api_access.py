#!/usr/bin/env python3
"""Check an owned Maps API key with at most one explicit, bounded request.

The default checks configuration only. --live may incur provider charges.
Returned content is transient: no photographs, photo resource names, review
prose or raw API payloads are written. Google Place IDs and availability counts
are the only content metadata in the report. Credentials never enter output.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
KEY_NAMES = {"google": "GOOGLE_PLACES_API_KEY", "2gis": "TWOGIS_API_KEY"}
GOOGLE_FIELDS = "places.id,places.displayName,places.location,places.rating,places.userRatingCount,places.photos,places.businessStatus,places.attributions"


def configured_key(provider: str, env_file: Path = ROOT / ".env") -> str | None:
    """Process secret injection wins; an explicitly empty value disables it."""
    name = KEY_NAMES[provider]
    if name in os.environ:
        return os.environ[name]
    return dotenv_values(env_file, interpolate=False).get(name)


def probe(provider: str, key: str | None, *, live: bool = False, query: str = "Байтерек Астана бульвар Нуржол 14",
          reviews: bool = False, transport=None) -> dict:
    if provider not in KEY_NAMES:
        raise ValueError("Unsupported provider")
    if not isinstance(query, str) or not 3 <= len(query.strip()) <= 300:
        raise ValueError("A short, named public-place query is required")
    key = key.strip() if isinstance(key, str) else ""
    report = {"provider": provider, "checked_at": datetime.now(timezone.utc).isoformat(),
              "configured": bool(key), "status": "not_configured" if not key else "configured",
              "request_count": 0, "http_status": None, "api_status": None,
              "credential_variable": KEY_NAMES[provider], "raw_payload_retained": False,
              "review_texts_retained": 0, "photo_assets_retained": 0,
              "scope": "One request proves only this endpoint/field-mask access, not citywide coverage or redistribution rights."}
    if not key or not live:
        return report
    if provider == "google":
        endpoint = "https://places.googleapis.com/v1/places:searchText"
        headers = {"X-Goog-Api-Key": key, "X-Goog-FieldMask": GOOGLE_FIELDS + (",places.reviews" if reviews else "")}
        payload = {"textQuery": query.strip(), "pageSize": 1, "languageCode": "ru",
                   "locationBias": {"circle": {"center": {"latitude": 51.1282882, "longitude": 71.4304546}, "radius": 5000}}}
        kwargs = {"json": payload, "headers": headers}
        method = "POST"
        report["requested_sku_level"] = "Text Search Enterprise + Atmosphere" if reviews else "Text Search Enterprise"
    else:
        endpoint = "https://catalog.api.2gis.com/3.0/items"
        kwargs = {"params": {"key": key, "q": query.strip(), "location": "71.4304546,51.1282882",
                             "fields": "items.point,items.reviews", "page_size": 1}}
        method = "GET"
    try:
        # No redirect can forward the server credential to another origin.
        with httpx.Client(timeout=20, follow_redirects=False, trust_env=False, transport=transport) as client:
            report["request_count"] = 1
            with client.stream(method, endpoint, **kwargs) as response:
                report["http_status"] = response.status_code
                if response.status_code != 200:
                    report["status"] = "denied" if response.status_code in {401, 403, 429} else "provider_unavailable"
                    report["api_status"] = "HTTP_" + str(response.status_code)
                    return report
                chunks, total = [], 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > 2_000_000:
                        report.update(status="invalid_response", api_status="RESPONSE_TOO_LARGE")
                        return report
                    chunks.append(chunk)
                content = json.loads(b"".join(chunks))
    except (httpx.HTTPError, ValueError, UnicodeError):
        # Provider/transport exception strings can include a credentialed URL.
        report.update(status="provider_unavailable", api_status="TRANSPORT_OR_JSON_ERROR")
        return report
    if not isinstance(content, dict):
        report.update(status="invalid_response", api_status="INVALID_JSON_SHAPE")
        return report
    if provider == "2gis":
        meta = content.get("meta", {})
        code = meta.get("code") if isinstance(meta, dict) else None
        if code != 200:
            report.update(status="denied", api_status="META_" + str(code) if type(code) is int else "META_ERROR")
            return report
        result = content.get("result", {})
        places = result.get("items", []) if isinstance(result, dict) else None
    else:
        if "error" in content:
            report.update(status="denied", api_status="PROVIDER_ERROR")
            return report
        places = content.get("places", [])
    if not isinstance(places, list) or any(not isinstance(place, dict) for place in places):
        report.update(status="invalid_response", api_status="INVALID_PLACE_LIST")
        return report
    places = places[:1]
    report.update(status="live_verified", api_status="OK", found_places=len(places),
                  requested_review_fields=bool(reviews and provider == "google"))
    if provider == "google":
        report["place_ids"] = [place["id"] for place in places if isinstance(place.get("id"), str)
                               and re.fullmatch(r"[A-Za-z0-9_-]{1,250}", place["id"]) and key not in place["id"]]
        report["fields_observed"] = {"rating": sum(type(place.get("rating")) in {int, float} for place in places),
                                     "rating_count": sum(type(place.get("userRatingCount")) is int for place in places),
                                     "photo_resources": sum(len(place["photos"]) for place in places if isinstance(place.get("photos"), list)),
                                     "review_samples": sum(len(place["reviews"]) for place in places if isinstance(place.get("reviews"), list))}
    else:
        report["fields_observed"] = {"point": sum(isinstance(place.get("point"), dict) for place in places),
                                     "review_statistics": sum(isinstance(place.get("reviews"), dict) for place in places)}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True, choices=KEY_NAMES)
    parser.add_argument("--live", action="store_true", help="Make one request; provider charges can apply")
    parser.add_argument("--reviews", action="store_true", help="Google only: request review samples; higher SKU applies")
    parser.add_argument("--query", default="Байтерек Астана бульвар Нуржол 14")
    args = parser.parse_args()
    if args.reviews and args.provider != "google":
        parser.error("2GIS API review-body retrieval is not promised by this probe")
    report = probe(args.provider, configured_key(args.provider), live=args.live, query=args.query, reviews=args.reviews)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"configured", "live_verified"} else 1


if __name__ == "__main__":
    sys.exit(main())
