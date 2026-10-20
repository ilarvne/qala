"""Validate public-card observations without turning them into open POI data.

Ratings from different providers are separate observations, not interchangeable
votes. Identity requires an exact local name/alias and nearby entity coordinates.
"""
from __future__ import annotations

from datetime import datetime
import math
import re
import unicodedata
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

HOSTS = {
    "2gis": {"2gis.kz", "www.2gis.kz"},
    "yandex": {"yandex.ru", "yandex.kz", "yandex.com"},
    "google": {"google.com", "www.google.com", "maps.google.com", "google.kz", "www.google.kz"},
}
FIELDS = ("provider", "provider_id", "source_url", "name", "lat", "lon", "address", "rating",
          "rating_scale", "rating_count", "review_count", "photo_source_links", "review_source_links",
          "observed_at", "access_method", "http_status", "evidence_sha256", "matched_poi_ids",
          "identity_evidence", "import_policy", "warnings")


def _credential_parameter(key):
    normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
    return (normalized.startswith(("xamz", "xgoog"))
            or normalized in {"key", "apikey", "accesskey", "token", "accesstoken", "refreshtoken",
                              "signature", "sig", "authorization", "auth", "clientsecret", "secret",
                              "session", "sessionid", "sessiontoken", "cookie", "credential", "credentials",
                              "password", "passwd", "xapikey"}
            or normalized.endswith(("token", "secret", "signature", "credential", "authorization")))


def _note(row, field, value):
    if value not in row[field]:
        row[field].append(value)


def _number(value, minimum, maximum):
    return value if not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and minimum <= value <= maximum else None


def _count(value):
    number = _number(value, 0, 1_000_000_000)
    return int(number) if number is not None and int(number) == number else None


def public_url(value):
    if not isinstance(value, str) or len(value) > 4000:
        return None
    try:
        url = urlsplit(value)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.port not in {None, 443}:
            return None
        if any(_credential_parameter(key) for key, _ in parse_qsl(url.query)):
            return None
        return urlunsplit((url.scheme, url.netloc, url.path, url.query, ""))
    except ValueError:
        return None


def source_url(value, provider):
    url = public_url(value)
    if not url:
        return None
    parts = urlsplit(url)
    if parts.hostname not in HOSTS[provider]:
        return None
    if provider == "2gis" and not re.fullmatch(r"/astana/firm/\d+/?(?:tab/(?:info|photos|reviews)/?)?", parts.path):
        return None
    if provider == "yandex" and not re.fullmatch(r"/maps/org/(?:[^/]+/)?\d+/?(?:reviews/|gallery/)?", parts.path):
        return None
    if provider == "google" and not parts.path.startswith("/maps"):
        return None
    # Keep only public place-addressing parameters; drop tracking/session state.
    query = urlencode([(key, val) for key, val in parse_qsl(parts.query) if key in {"cid", "q", "query", "query_place_id", "api"}]) if provider == "google" else ""
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def validate_observation(record: dict) -> dict:
    """Copy only allowlisted factual fields; never carry scraped page state."""
    if not isinstance(record, dict) or record.get("provider") not in HOSTS:
        raise ValueError("Unknown provider observation")
    provider = record["provider"]
    url = source_url(record.get("source_url"), provider)
    identifier, name = record.get("provider_id"), record.get("name")
    if not url or not isinstance(identifier, str) or not identifier.strip() or len(identifier) > 250 or not isinstance(name, str) or not name.strip() or len(name) > 500:
        raise ValueError("Observation lacks a public entity identity")
    if provider in {"2gis", "yandex"}:
        pattern = r"/firm/(\d+)" if provider == "2gis" else r"/org/(?:[^/]+/)?(\d+)"
        path_id = re.search(pattern, urlsplit(url).path)
        if not path_id or path_id[1] != identifier:
            raise ValueError("Entity ID differs from the public source URL")
    else:
        parts = urlsplit(url)
        ids = re.findall(r"!1s([^!/?]+)", unquote(parts.path))
        query = dict(parse_qsl(parts.query))
        ids += [query[key] for key in ("cid", "query_place_id") if key in query]
        if identifier not in ids:
            raise ValueError("Google entity ID differs from the public source URL")
    if record.get("import_policy") != "evaluation_only":
        raise ValueError("Public-card extraction is not a redistribution licence")
    try:
        observed = datetime.fromisoformat(record["observed_at"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Observation requires its original acquisition time") from exc
    if observed.tzinfo is None or record.get("access_method") not in {"http", "browser", "exa"}:
        raise ValueError("Observation lacks explicit time zone or acquisition method")
    digest = record.get("evidence_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("Observation lacks a source evidence digest")
    if record.get("rating_scale") != 5:
        raise ValueError("Unknown rating scale; do not silently rescale")
    row = {key: record.get(key) for key in FIELDS}
    row.update(source_url=url, provider_id=identifier.strip(), name=name.strip(), matched_poi_ids=[])
    row["lat"], row["lon"] = _number(row["lat"], -90, 90), _number(row["lon"], -180, 180)
    if row["lat"] is None or row["lon"] is None:
        row["lat"] = row["lon"] = None
    row["rating"] = _number(row["rating"], 0, 5)
    row["rating_count"], row["review_count"] = _count(row["rating_count"]), _count(row["review_count"])
    row["address"] = row["address"][:1000] if isinstance(row["address"], str) else None
    for key in ("photo_source_links", "review_source_links"):
        values = row[key] if isinstance(row[key], list) else []
        row[key] = list(dict.fromkeys(url for item in values[:50] if (url := public_url(item))))
    for key in ("identity_evidence", "warnings"):
        row[key] = list(dict.fromkeys(value[:1000] for value in (row[key] if isinstance(row[key], list) else [])[:30] if isinstance(value, str)))
    row["http_status"] = int(row["http_status"]) if _number(row["http_status"], 100, 599) is not None else None
    if row["access_method"] == "exa":
        _note(row, "warnings", "Search-index evidence is not a fresh direct provider response.")
    return row


def normalized_name(value):
    text = "".join(c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c))
    text = " ".join(re.findall(r"[^\W_]+", text))
    # A conventional country abbreviation is not a fuzzy venue-name match.
    return re.sub(r"\bмузеи рк\b", "музеи республики казахстан", text)


def local_names(poi):
    names = [poi.get("name", "")]
    names += list(poi.get("names", {}).values())
    names += poi.get("aliases", [])
    names += [value for key, value in poi.get("raw_tags", {}).items() if key == "name" or key.startswith(("name:", "alt_name", "official_name", "short_name"))]
    return {normalized_name(name) for value in names if isinstance(value, str) for name in value.split(";") if name.strip()}


def distance_m(lat, lon, other_lat, other_lon):
    a, b = math.radians(lat), math.radians(other_lat)
    value = math.sin((b - a) / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(math.radians(other_lon - lon) / 2) ** 2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(value)))


def correlate(row: dict, pois: list[dict], max_distance_m: float = 200) -> dict:
    """Require both name and coordinates; ambiguous nearby branches stay apart."""
    row = validate_observation(row)
    if row["lat"] is None or row["access_method"] == "exa":
        _note(row, "warnings", "Local identity not assigned without direct entity coordinates and acquisition.")
        return row
    target, matches = normalized_name(row["name"]), []
    for poi in pois:
        if target not in local_names(poi):
            continue
        delta = distance_m(row["lat"], row["lon"], poi["lat"], poi["lon"])
        if delta <= max_distance_m:
            matches.append((delta, poi["id"]))
    if len(matches) == 1:
        delta, identifier = matches[0]
        row["matched_poi_ids"] = [identifier]
        _note(row, "identity_evidence", f"Exact local multilingual name/alias and entity-coordinate distance {delta:.1f} m.")
    elif matches:
        _note(row, "warnings", "Multiple nearby local identities share this name; no automatic match.")
    else:
        _note(row, "warnings", "No exact local name/alias within the coordinate tolerance; no automatic match.")
    return row
