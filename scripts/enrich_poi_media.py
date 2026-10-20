#!/usr/bin/env python3
"""Resolve exact OSM → Wikidata/Commons links to real, attributed photographs.

No search-by-similar-name images, generated pictures, unlicensed operator photos,
review scraping, or Google Places content enter the reusable open dataset.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
import os
import unicodedata
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = os.getenv("QALA_DATA_USER_AGENT", "QalaResearch/2.0 (https://www.openstreetmap.org/relation/3087155; Astana open walking dataset)")
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"


def canonical_file_title(title: str) -> str:
    return unicodedata.normalize("NFC", title.replace("_", " ").strip())


def place_photo_title(title: str) -> bool:
    """Reject explicit non-photographic/place-identity pitfalls before export."""
    return not re.search(r"\b(?:stamps?|banknotes?|portrait|logo|coat of arms|destination map|construction|rendering)\b|\bISS\d+|Dmitry Medvedev|Nazarbayev.*visits", title, re.I)


def category_file_score(title: str, category: str, targets: list[dict]) -> int:
    """Prefer place views, never banknotes, portraits or event press images."""
    normalize = lambda value: "".join(c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c))
    title = normalize(title)
    if re.search(r"tenge|kzt|averse|banknote|stamps?|portrait|president|visits|construction|policebox|exhibition people|wikimedian|staff|kabinbekova|tour guide|drawings|plan of|map of|destination map|pamorama", title):
        return -1
    words = set(re.findall(r"[\w]+", normalize(category + " " + " ".join(p["name"] for p in targets))))
    words -= {"file", "category", "astana", "kazakhstan", "republic", "the", "of", "and", "el"}
    return sum(len(word) for word in words if len(word) >= 4 and word in title)


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data):
        self.parts.append(data)


def clean_html(value: str | None) -> str:
    parser = PlainText()
    parser.feed(value or "")
    return " ".join(html.unescape(" ".join(parser.parts)).split())


def api(client: httpx.Client, url: str, params: dict) -> dict:
    for attempt in range(3):
        response = client.get(url, params={"format": "json", "maxlag": 5, **params})
        if response.status_code in {429, 503} and attempt < 2:
            retry = response.headers.get("retry-after", "")
            try:
                pause = float(retry)
            except ValueError:
                pause = 5 * 2 ** attempt
            if pause > 55:
                # Avoid occupying a process on an unbounded public-service
                # refusal. Record the failure and preserve existing sources.
                response.raise_for_status()
            time.sleep(max(5, pause))
            continue
        response.raise_for_status()
        result = response.json()
        if result.get("error"):
            raise ValueError(str(result["error"].get("code", "API error")))
        time.sleep(0.4)  # serial; below identified client's public API limit
        return result
    raise ValueError("API retries exhausted")


def commons_photo(page: dict, observed: str) -> dict | None:
    info = next(iter(page.get("imageinfo", [])), None)
    if not info or info.get("mime") not in {"image/jpeg", "image/png", "image/webp"}:
        return None
    meta = info.get("extmetadata", {})
    get = lambda key: clean_html(meta.get(key, {}).get("value"))
    license_name, license_url = get("LicenseShortName"), get("LicenseUrl")
    if get("NonFree").casefold() == "true" or get("DeletionReason"):
        return None
    # Commons metadata can be incomplete or multi-licensed. Retain only a
    # clearly identified reusable CC/public-domain choice and its source page.
    # An NC/ND licence is not a reusable Commons CC BY/CC BY-SA choice.
    # Prefix matching previously also admitted names such as CC BY-NC 4.0.
    reusable = bool(re.fullmatch(r"cc by(?:-sa)?\s+\d+(?:\.\d+)?", license_name.casefold())) or license_name.casefold().startswith(("cc0", "public domain", "pd", "pdm"))
    author = get("Artist")
    if not reusable or not license_name or (get("AttributionRequired").casefold() == "true" and not author):
        return None
    if not license_url:
        if license_name.casefold().startswith(("public domain", "pd", "pdm")):
            license_url = "https://creativecommons.org/publicdomain/mark/1.0/"
        else:
            return None
    if license_url.startswith("//"):
        license_url = "https:" + license_url
    parsed_license = urlsplit(license_url)
    if (parsed_license.scheme not in {"https", "http"} or parsed_license.hostname not in {"creativecommons.org", "www.creativecommons.org"}
            or not re.fullmatch(r"/(?:licenses/(?:by|by-sa)/\d+(?:\.\d+)?(?:/[a-z]{2})?|publicdomain/(?:zero|mark)/1\.0)(?:/deed\.[a-z-]+)?/?", parsed_license.path)):
        return None
    source_url = info.get("descriptionurl") or "https://commons.wikimedia.org/wiki/" + quote(page["title"].replace(" ", "_"))
    return {
        "url": info["url"], "thumbnail_url": info.get("thumburl") or info["url"],
        "source_url": source_url, "title": clean_html(page["title"].removeprefix("File:")),
        "author": author or "Wikimedia Commons contributor", "license": license_name,
        "license_url": license_url,
        "attribution": get("Attribution") or f"{author or 'Wikimedia Commons contributor'} · {license_name}",
        "provider": "Wikimedia Commons", "observed_at": observed,
        "width": info.get("width"), "height": info.get("height"),
        "restrictions": get("Restrictions") or None,
    }


def enrich_media(dataset: dict, cache_dir: Path | None = None, max_photos: int = 2, *,
                 raw_dir: Path | None = None, entities_override: dict | None = None,
                 additional_titles: dict[str, list[str]] | None = None) -> None:
    observed = datetime.now(timezone.utc).isoformat()
    pois = dataset["pois"]
    curation_path = ROOT / "data/photo-curation.json"
    curation = json.loads(curation_path.read_text()) if curation_path.exists() else {}
    curated = curation.get("preferred_files_by_poi", {})
    excluded_files = {canonical_file_title(title) for title in curation.get("excluded_files", {})}
    # A temporary upstream failure must not erase already attributed media.
    # Exact source links are deduplicated below; callers stage publication.
    for poi in pois:
        poi["photos"] = [photo for photo in poi.get("photos", []) if
                         canonical_file_title("File:" + photo.get("title", "")) not in excluded_files
                         and place_photo_title(photo.get("title", ""))]
        poi["image"] = poi["photos"][0]["url"] if poi["photos"] else None
    entity_ids = sorted({p["wikidata"] for p in pois if re.fullmatch(r"Q\d+", p.get("wikidata") or "")})
    entities, errors, snapshots = dict(entities_override or {}), [], {}
    with httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        missing_entity_ids = [qid for qid in entity_ids if qid not in entities]
        for start in range(0, len(missing_entity_ids), 40):
            try:
                result = api(client, WIKIDATA_API, {"action": "wbgetentities", "ids": "|".join(missing_entity_ids[start:start + 40]), "props": "claims|descriptions|labels"})
                entities.update(result.get("entities", {}))
                snapshots[f"wikidata-{start // 40}"] = result
            except (httpx.HTTPError, ValueError) as exc:
                errors.append(f"Wikidata batch {start // 40}: {type(exc).__name__}")
        title_pois: dict[str, list[dict]] = {}
        preferred_titles: set[str] = set()
        categories: dict[str, list[dict]] = {}
        for poi in pois:
            tags = poi.get("raw_tags", {})
            for title in (additional_titles or {}).get(poi["id"], []):
                title_pois.setdefault(title, []).append(poi)
                preferred_titles.add(title)
            for title in curated.get(poi["id"], []):
                title_pois.setdefault(title, []).append(poi)
                preferred_titles.add(title)
            linked = tags.get("wikimedia_commons", "")
            if linked.startswith("File:"):
                title_pois.setdefault(linked, []).append(poi)
                preferred_titles.add(linked)
            elif linked.startswith("Category:"):
                categories.setdefault(linked, []).append(poi)
            entity = entities.get(poi.get("wikidata"), {})
            descriptions = {language: item["value"] for language, item in entity.get("descriptions", {}).items() if language in {"en", "ru", "kk"}}
            if descriptions:
                poi["descriptions"] = descriptions
                # Preserve independently verified operator descriptions. A
                # Wikidata statement is source text, not a model's venue claim.
                if poi.get("description_derived") and descriptions.get("en"):
                    poi["description"] = descriptions["en"]
                    poi["description_derived"] = False
                    poi["description_source"] = {"name": "Wikidata", "url": "https://www.wikidata.org/wiki/" + entity["id"], "collected_at": observed, "license": "CC0", "license_url": "https://creativecommons.org/publicdomain/zero/1.0/"}
            for statement in entity.get("claims", {}).get("P18", [])[:max_photos]:
                filename = statement.get("mainsnak", {}).get("datavalue", {}).get("value")
                if filename and statement.get("rank") != "deprecated":
                    title_pois.setdefault("File:" + filename, []).append(poi)
                    preferred_titles.add("File:" + filename)
            # P373 categories are a source-asserted place link, not nearby or
            # fuzzy-name matches. Files are limited to this direct category.
            if not linked:
                for statement in entity.get("claims", {}).get("P373", [])[:1]:
                    category = statement.get("mainsnak", {}).get("datavalue", {}).get("value")
                    if category:
                        categories.setdefault("Category:" + category, []).append(poi)
        for category, targets in categories.items():
            try:
                result = api(client, COMMONS_API, {"action": "query", "list": "categorymembers", "cmtitle": category, "cmtype": "file", "cmlimit": 100})
                snapshots["category-" + hashlib.sha256(category.encode()).hexdigest()[:12]] = result
                members = result.get("query", {}).get("categorymembers", [])
                members = sorted(members, key=lambda item: (-category_file_score(item["title"], category, targets), item["title"]))
                for item in [item for item in members if category_file_score(item["title"], category, targets) > 0][:3]:
                    title_pois.setdefault(item["title"], []).extend(targets)
            except (httpx.HTTPError, ValueError) as exc:
                errors.append(f"{category}: {type(exc).__name__}")
        # Explicit P18/file links are stronger evidence than category member
        # order. Process them first so an alphabetically early museum object,
        # currency reproduction or construction image cannot become the cover.
        curated_order = {title: index for titles in curated.values() for index, title in enumerate(titles)}
        titles = sorted({title for title in title_pois if canonical_file_title(title) not in excluded_files and place_photo_title(title)}, key=lambda title: (title not in curated_order, curated_order.get(title, 0), title not in preferred_titles, title))
        for start in range(0, len(titles), 5):
            try:
                result = api(client, COMMONS_API, {"action": "query", "titles": "|".join(titles[start:start + 5]), "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1000, "iiextmetadatafilter": "Artist|Attribution|AttributionRequired|LicenseShortName|LicenseUrl|NonFree|DeletionReason|Restrictions"})
                snapshots[f"commons-{start // 5}"] = result
                # Follow normalization when file names use underscores or case.
                normalized = {item["to"]: item["from"] for item in result.get("query", {}).get("normalized", [])}
                for page in result.get("query", {}).get("pages", {}).values():
                    # MediaWiki normalizes underscores and Unicode in requested
                    # titles. Apply curation again to the canonical response.
                    if canonical_file_title(page["title"]) in excluded_files or not place_photo_title(page["title"]):
                        continue
                    photo = commons_photo(page, observed)
                    if not photo:
                        continue
                    targets = title_pois.get(page["title"], []) or title_pois.get(normalized.get(page["title"], ""), [])
                    if cache_dir is not None:
                        try:
                            response = client.get(photo["thumbnail_url"])
                            response.raise_for_status()
                            if not response.headers.get("content-type", "").startswith("image/") or len(response.content) > 3_000_000:
                                raise ValueError("invalid or oversized photograph")
                            suffix = ".png" if "png" in response.headers.get("content-type", "") else ".webp" if "webp" in response.headers.get("content-type", "") else ".jpg"
                            filename = hashlib.sha256(photo["source_url"].encode()).hexdigest()[:20] + suffix
                            cache_dir.mkdir(parents=True, exist_ok=True)
                            (cache_dir / filename).write_bytes(response.content)
                            photo["original_url"] = photo["url"]
                            photo["remote_thumbnail_url"] = photo["thumbnail_url"]
                            photo["url"] = photo["thumbnail_url"] = "/photos/" + filename
                        except (httpx.HTTPError, ValueError) as exc:
                            errors.append(f'{page["title"]} thumbnail cache: {type(exc).__name__}')
                    for poi in targets:
                        photos = poi.setdefault("photos", [])
                        if len(photos) < max_photos and photo["source_url"] not in {p["source_url"] for p in photos}:
                            photos.append(dict(photo))
                            poi["image"] = photos[0]["url"]
            except (httpx.HTTPError, ValueError) as exc:
                errors.append(f"Commons batch {start // 5}: {type(exc).__name__}")
    raw_dir = raw_dir if raw_dir is not None else ROOT / "data/raw/media"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for name, snapshot in snapshots.items():
        (raw_dir / f"{name}.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))
    dataset["metadata"]["media_enrichment"] = {
        "collected_at": observed, "provider": "Wikimedia Commons / Wikidata exact entity links",
        "entity_count": len(entities), "candidate_file_count": len(title_pois),
        "pois_with_photos": sum(bool(p.get("photos")) for p in pois),
        "photo_count": sum(len(p.get("photos", [])) for p in pois), "errors": errors,
        "curation_file": "data/photo-curation.json", "curation": "Source-exact files visually checked; stale construction, people, diagrams and misleading category images excluded.",
        "policy": "Per-file reusable license and plaintext author attribution retained; no fuzzy-name or nearby-photo assignment.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/pois.json")
    parser.add_argument("--cache", action="store_true", help="Save bounded photographic thumbnails into public/photos")
    args = parser.parse_args()
    dataset = json.loads(args.input.read_text())
    enrich_media(dataset, ROOT / "public/photos" if args.cache else None)
    from collect_pois import coverage, write_json
    dataset["metadata"]["coverage"] = coverage(dataset["pois"])
    write_json(args.input, dataset)
    manifest = {"metadata": dataset["metadata"]["media_enrichment"], "photos": [{"poi_id": p["id"], "poi_name": p["name"], **photo} for p in dataset["pois"] for photo in p.get("photos", [])]}
    write_json(ROOT / "data/photo-attributions.json", manifest)
    print(json.dumps(dataset["metadata"]["media_enrichment"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
