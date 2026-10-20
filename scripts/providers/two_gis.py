"""Extract bounded factual evidence from already acquired public 2GIS cards.

This module performs no network requests and does not extract review prose,
authors, private application state or authorization tokens. Its output is a
research sidecar, not permission to redistribute a provider's database/media.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit


MAX_HTML_BYTES = 4 * 1024 * 1024
_CARD = re.compile(r"^/astana/firm/([0-9]{8,20})(?:/tab/(?:info|photos|reviews|prices))?/?$")
_COUNT = re.compile(r"^([0-9][0-9\s\u00a0\u202f]*)\s+оцен(?:ок|ки|ка|ку|кой)$", re.I)
_NUMBER = re.compile(r"^[0-9]+(?:[.,][0-9]+)?$")


class _PublicCard(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.metadata: dict[str, str] = {}
        self.tokens: list[str] = []
        self.headings: list[tuple[str, int]] = []
        self._skip = 0
        self._heading: list[str] | None = None
        self._heading_index = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag in {"script", "style"}:
            self._skip += 1
        if tag == "meta":
            key = values.get("property") or values.get("name")
            if key in {"og:title", "og:description", "og:image"}:
                self.metadata.setdefault(key, values.get("content") or "")
        if tag == "h1" and not self._skip:
            self._heading = []
            self._heading_index = len(self.tokens)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self._skip = max(0, self._skip - 1)
        if tag == "h1" and self._heading is not None:
            self.headings.append((" ".join(self._heading).strip(), self._heading_index))
            self._heading = None

    def handle_data(self, data: str) -> None:
        if self._skip or not data.strip():
            return
        token = " ".join(data.split())
        self.tokens.append(token)
        if self._heading is not None:
            self._heading.append(token)


def _integer(value: str) -> int | None:
    cleaned = re.sub(r"[\s\u00a0\u202f]", "", value)
    if cleaned.isdigit() and len(cleaned) <= 9:
        number = int(cleaned)
        return number if number <= 100_000_000 else None
    return None


def _rating(value: str) -> float | None:
    if not _NUMBER.fullmatch(value):
        return None
    number = float(value.replace(",", "."))
    return number if math.isfinite(number) and 0 <= number <= 5 else None


def _tab_count(tokens: list[str], label: str) -> int | None:
    for index, token in enumerate(tokens[:-1]):
        if token == label:
            return _integer(tokens[index + 1])
    return None


def parse_html(html: str, url: str, *, observed_at: str | None = None) -> list[dict]:
    """Parse one exact Astana firm card, rejecting challenge/unrelated pages.

    Counts in the visible card take precedence over Open Graph metadata because
    the two were observed to disagree in the same successful HTTP response.
    Map-share image coordinates identify the card's map centre, not an entrance.
    ``observed_at`` is the original acquisition time, never the parse time.
    """
    try:
        target = urlsplit(url)
        port = target.port
    except ValueError:
        return []
    match = _CARD.fullmatch(target.path)
    if target.scheme != "https" or target.hostname not in {"2gis.kz", "www.2gis.kz"}:
        return []
    if target.username or target.password or port not in {None, 443} or not match:
        return []
    if len(html.encode("utf-8")) > MAX_HTML_BYTES:
        raise ValueError("2GIS HTML exceeds the 4 MiB evidence limit")
    # A returned challenge must never become a POI named "2GIS Captcha".
    if re.search(r"<title[^>]*>[^<]*(?:captcha|капч|проверка)", html, re.I):
        return []
    parser = _PublicCard()
    parser.feed(html)
    if len(parser.headings) != 1 or not parser.metadata.get("og:title"):
        return []
    name, start = parser.headings[0]
    if not name or name.casefold() not in parser.metadata["og:title"].casefold():
        return []
    provider_id = match.group(1)
    source_url = f"https://2gis.kz/astana/firm/{provider_id}"
    header = parser.tokens[start:start + 60]
    rating, rating_count = None, None
    for index, token in enumerate(header[:20]):
        if token in {"Контакты", "Инфо", "Отзывы", "Фото"}:
            break
        count = _COUNT.fullmatch(token)
        if count:
            rating_count = _integer(count.group(1))
            if index:
                rating = _rating(header[index - 1])
            break
    description = parser.metadata.get("og:description", "")
    og_rating = re.search(r"Оценка\s+([0-9]+(?:[.,][0-9]+)?)", description)
    og_photos = re.search(r"([0-9][0-9\s\u00a0\u202f]*)\s+фото", description)
    og_reviews = re.search(r"([0-9][0-9\s\u00a0\u202f]*)\s+отзыв", description)
    warnings = [
        "provider_reuse_permission_not_granted",
        "photo_and_review_links_are_references_not_licensed_assets",
    ]
    if not isinstance(observed_at, str) or not observed_at.strip():
        observed_at = None
        warnings.append("Original acquisition time is unknown; parsing cached content does not establish freshness.")
    if rating is None and og_rating:
        rating = _rating(og_rating.group(1))
        warnings.append("rating_from_open_graph_only")
    elif og_rating and rating != _rating(og_rating.group(1)):
        warnings.append("visible_rating_differs_from_open_graph")
    review_count = _tab_count(header, "Отзывы")
    photo_count = _tab_count(header, "Фото")
    metadata_review_count = _integer(og_reviews.group(1)) if og_reviews else None
    metadata_photo_count = _integer(og_photos.group(1)) if og_photos else None
    if review_count is None:
        review_count = metadata_review_count
    elif metadata_review_count is not None and metadata_review_count != review_count:
        warnings.append("visible_review_count_differs_from_open_graph")
    if photo_count is None:
        photo_count = metadata_photo_count
    elif metadata_photo_count is not None and metadata_photo_count != photo_count:
        warnings.append("visible_photo_count_differs_from_open_graph")
    lat = lon = None
    address = None
    identity = ["exact Astana firm ID in source URL", "visible H1 agrees with Open Graph title"]
    share_image = urlsplit(parser.metadata.get("og:image", ""))
    if share_image.scheme == "https" and share_image.hostname == "beautyshare.2gis.ru":
        query = parse_qs(share_image.query)
        center = query.get("center", [""])[0].split(",")
        if len(center) == 2:
            try:
                parsed_lon, parsed_lat = map(float, center)
                # A deliberately generous Astana bounding box; no remote city.
                if 70.9 <= parsed_lon <= 71.9 and 50.8 <= parsed_lat <= 51.5:
                    lon, lat = parsed_lon, parsed_lat
                    identity.append("coordinates from public Open Graph share-image centre; not entrance geometry")
            except ValueError:
                pass
        raw_address = query.get("desc", [""])[0]
        address = " ".join(unescape(re.sub(r"<[^>]*>", " ", raw_address)).split()) or None
    photos = [source_url + "/tab/photos"]
    # Only the explicitly ID-bound branch cover is retained. Other image URLs
    # in hydration data may belong to recommendations, adverts or reviewers.
    normalised = html.replace("\\/", "/")
    cover_pattern = re.compile(
        r"https://i[0-9]+\.photo\.2gis\.com/main/branch/[0-9]+/"
        + re.escape(provider_id) + r"/common(?=[\s\"'<>\\]|$)"
    )
    for cover in cover_pattern.findall(normalised):
        if cover not in photos:
            photos.append(cover)
    if photo_count is not None:
        identity.append(f"visible photo tab count: {photo_count}; Open Graph photo count: {metadata_photo_count}")
    if review_count is not None:
        identity.append(f"visible text-review tab count: {review_count}; Open Graph text-review count: {metadata_review_count}")
    return [{
        "provider": "2gis", "provider_id": provider_id, "source_url": source_url,
        "name": name, "lat": lat, "lon": lon, "address": address,
        "rating": rating, "rating_scale": 5, "rating_count": rating_count,
        "review_count": review_count, "photo_source_links": photos,
        "review_source_links": [source_url + "/tab/reviews"],
        "observed_at": observed_at,
        "access_method": "http", "http_status": None,
        "evidence_sha256": sha256(html.encode("utf-8")).hexdigest(),
        "matched_poi_ids": [], "identity_evidence": identity,
        "import_policy": "evaluation_only", "warnings": warnings,
    }]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", type=Path, required=True, help="Already acquired, private local HTML")
    parser.add_argument("--url", required=True)
    parser.add_argument("--observed-at", required=True, help="Original acquisition time as ISO 8601 with timezone; not the time of reparsing")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        original_time = datetime.fromisoformat(args.observed_at.replace("Z", "+00:00"))
        if original_time.tzinfo is None:
            raise ValueError("Timezone is required")
    except ValueError:
        parser.error("--observed-at must be the original acquisition timestamp in ISO 8601 with a timezone")
    if args.html.stat().st_size > MAX_HTML_BYTES:
        parser.error("HTML exceeds 4 MiB")
    rows = parse_html(args.html.read_text(encoding="utf-8"), args.url, observed_at=args.observed_at)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"rows": len(rows), "output": str(args.out)}))


if __name__ == "__main__":
    main()
