#!/usr/bin/env python3
"""Stage explicitly reviewed venue photographs; never search or publish a corpus.

The seed document binds a named local source record to exact Commons file names
and a review of the file's actual description. This is an editorial crosswalk,
not an automatic nearby-image matcher. Metadata acquisition is bounded, serial,
resumable and stops on the first HTTP/API error. Compilation is network-free.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

import httpx

try:
    from scripts.enrich_poi_media import canonical_file_title, clean_html, commons_photo, place_photo_title, USER_AGENT
    from scripts.providers.crawl_state import atomic_json_write
except ModuleNotFoundError:
    from enrich_poi_media import canonical_file_title, clean_html, commons_photo, place_photo_title, USER_AGENT
    from providers.crawl_state import atomic_json_write

ROOT = Path(__file__).resolve().parents[1]
API_URL = "https://commons.wikimedia.org/w/api.php"
MAX_SEEDS = 24
MAX_FILES = 48
MAX_RESPONSE = 3_000_000
atomic_write_json = atomic_json_write


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def target_fingerprint(poi: dict) -> str:
    return digest({key: poi.get(key) for key in ("id", "name", "names", "lat", "lon", "category", "poi_type", "source")})


def acquired(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Original acquisition time must be a string")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Acquisition time must include its original time zone")
    return value


def validate_seeds(seeds: object, dataset: dict) -> list[dict]:
    if not isinstance(seeds, list) or not 1 <= len(seeds) <= MAX_SEEDS:
        raise ValueError("Select one to 24 explicit named local places")
    by_id = {poi["id"]: poi for poi in dataset["pois"]}
    seen, checked = set(), []
    for seed in seeds:
        if not isinstance(seed, dict) or seed.get("poi_id") not in by_id or seed["poi_id"] in seen:
            raise ValueError("Unknown or duplicated local identity")
        poi = by_id[seed["poi_id"]]
        if poi.get("name_derived") or not poi.get("source", {}).get("url"):
            raise ValueError("Editorial source assignments require an existing named source record")
        if seed.get("target_fingerprint") != target_fingerprint(poi):
            raise ValueError("Reviewed local identity/facts changed; review again before compilation")
        files = seed.get("files")
        if not isinstance(files, list) or not 1 <= len(files) <= 2:
            raise ValueError("Choose at most two exact files per named place")
        titles = set()
        if sum(file.get("preferred_cover") is True for file in files if isinstance(file, dict)) > 1:
            raise ValueError("Choose only one preferred cover per named place")
        for file in files:
            if not isinstance(file, dict):
                raise ValueError("Each file requires explicit editorial identity evidence")
            if "preferred_cover" in file and not isinstance(file["preferred_cover"], bool):
                raise ValueError("Preferred cover must be a boolean editorial choice")
            title = file.get("title", "")
            if (not isinstance(title, str) or not title.startswith("File:") or "|" in title
                    or not re.search(r"\.(?:jpe?g|png|webp)$", title, re.I) or not place_photo_title(title)):
                raise ValueError("Unsupported exact source file")
            if canonical_file_title(title) in titles:
                raise ValueError("Duplicate exact source file")
            titles.add(canonical_file_title(title))
            evidence = file.get("identity", {})
            if (evidence.get("method") != "editorially_reviewed_named_venue"
                    or evidence.get("local_source_url") != poi["source"]["url"]
                    or evidence.get("local_name") != poi["name"]
                    or not isinstance(evidence.get("source_description"), str)
                    or len(evidence["source_description"].strip()) < 8
                    or not isinstance(evidence.get("review_note"), str) or len(evidence["review_note"].strip()) < 20):
                raise ValueError("Incomplete editorial source identity review")
            acquired(evidence.get("reviewed_at", ""))
        seen.add(seed["poi_id"])
        checked.append(deepcopy(seed))
    return checked


def collect_metadata(seeds: list[dict], out: Path, *, client=None, clock=time.monotonic, sleep=time.sleep) -> dict:
    """At most three API requests; existing captures and their dates are retained."""
    out.mkdir(parents=True, exist_ok=True)
    stop = out / "acquisition-stop.json"
    if stop.exists():
        raise ValueError("Previous acquisition stopped; inspect the retained provider response before a new campaign")
    titles = sorted({canonical_file_title(file["title"]) for seed in seeds for file in seed["files"]})
    if len(titles) > MAX_FILES:
        raise ValueError("Too many explicit files")
    owns = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(25, connect=5), follow_redirects=False,
                                   headers={"User-Agent": USER_AGENT}, trust_env=False)
    last, captures = None, []
    try:
        for offset in range(0, len(titles), 20):
            batch = titles[offset:offset + 20]
            key = digest(batch)[:16]
            target = out / ("commons-" + key + ".json")
            if target.exists():
                stored = json.loads(target.read_text())
                if (stored.get("source_url") != API_URL or stored.get("http_status") != 200
                        or stored.get("requested_titles") != batch or digest(stored.get("response")) != stored.get("response_sha256")):
                    raise ValueError("Retained source capture differs from requested exact files")
                acquired(stored["observed_at"])
                captures.append(target.name)
                continue
            if last is not None:
                pause = 10 - (clock() - last)
                if pause > 0:
                    sleep(pause)
            last = clock()
            params = {"action": "query", "format": "json", "maxlag": 5, "titles": "|".join(batch),
                      "prop": "imageinfo|categories|coordinates", "cllimit": 50,
                      "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1000,
                      "iiextmetadatafilter": "Artist|Attribution|AttributionRequired|LicenseShortName|LicenseUrl|NonFree|DeletionReason|Restrictions|ImageDescription|Categories"}
            status = None
            try:
                with client.stream("GET", API_URL, params=params) as response:
                    status = response.status_code
                    if status != 200:
                        raise ValueError("http_" + str(status))
                    payload = bytearray()
                    for block in response.iter_bytes():
                        payload.extend(block)
                        if len(payload) > MAX_RESPONSE:
                            raise ValueError("response_too_large")
                    body = json.loads(payload)
                    if not isinstance(body, dict) or body.get("error") or not isinstance(body.get("query", {}).get("pages"), dict):
                        raise ValueError("api_error_or_invalid_schema")
                stamp = datetime.now(timezone.utc).isoformat()
                atomic_write_json(target, {"source_url": API_URL, "requested_titles": batch,
                    "observed_at": stamp, "http_status": status, "response_sha256": digest(body), "response": body})
                captures.append(target.name)
            except (httpx.HTTPError, ValueError, json.JSONDecodeError):
                atomic_write_json(stop, {"source_url": API_URL, "observed_at": datetime.now(timezone.utc).isoformat(),
                    "http_status": status, "decision": "stop_without_retry", "requested_titles": batch})
                raise
    finally:
        if owns:
            client.close()
    return {"captures": captures, "requested_files": len(titles)}


def load_captures(directory: Path) -> dict[str, tuple[dict, dict]]:
    pages = {}
    for path in sorted(directory.glob("commons-*.json")):
        capture = json.loads(path.read_text())
        if (capture.get("source_url") != API_URL or capture.get("http_status") != 200
                or digest(capture.get("response")) != capture.get("response_sha256")):
            raise ValueError("Invalid retained Commons acquisition")
        acquired(capture["observed_at"])
        for page in capture["response"].get("query", {}).get("pages", {}).values():
            title = canonical_file_title(page.get("title", ""))
            if title in pages and pages[title][1]["observed_at"] != capture["observed_at"]:
                raise ValueError("Multiple acquisitions for one exact file require explicit selection")
            pages[title] = (page, {"snapshot": path.name, "observed_at": capture["observed_at"], "response_sha256": capture["response_sha256"]})
    return pages


def compile_sidecar(dataset: dict, seeds: object, captures: dict[str, tuple[dict, dict]]) -> dict:
    """Check retained licences/descriptions and emit data for separate publication."""
    checked = validate_seeds(seeds, dataset)
    by_id = {poi["id"]: poi for poi in dataset["pois"]}
    assignments, held = [], []
    for seed in checked:
        poi = by_id[seed["poi_id"]]
        for file in seed["files"]:
            title = canonical_file_title(file["title"])
            if title not in captures:
                held.append({"poi_id": poi["id"], "title": title, "reason": "metadata_not_acquired"})
                continue
            page, acquisition = captures[title]
            info = next(iter(page.get("imageinfo", [])), {})
            meta = info.get("extmetadata", {})
            description = clean_html(meta.get("ImageDescription", {}).get("value", ""))
            expected = " ".join(file["identity"]["source_description"].split())
            categories = (" ".join(c.get("title", "") for c in page.get("categories", [])) + " "
                          + meta.get("Categories", {}).get("value", "") + " " + clean_html(meta.get("Restrictions", {}).get("value", "")))
            if re.search(r"no[ _-]?fop|copyright[ _-]?(?:violation|warning)|deletion[ _-]?(?:requests?|pending)|non[ _-]?free", categories, re.I):
                held.append({"poi_id": poi["id"], "title": title, "reason": "source_rights_warning"})
                continue
            photo = commons_photo(page, acquisition["observed_at"])
            if not photo or expected not in description:
                held.append({"poi_id": poi["id"], "title": title, "reason": "licence_or_exact_description_not_verified"})
                continue
            assignments.append({"poi_id": poi["id"], "target_fingerprint": target_fingerprint(poi), "photo": photo,
                "identity": deepcopy(file["identity"]), "source_metadata": deepcopy(acquisition),
                "preferred_cover": file.get("preferred_cover", False),
                "source_description_sha256": hashlib.sha256(description.encode()).hexdigest()})
    return {"schema_version": 1, "kind": "curated_commons_assignments", "assignments": assignments, "held": held,
        "policy": "Explicit editorial named-venue crosswalk; original source acquisition dates; per-file reusable rights; no proximity-only, generated, brand or unrelated-city images; staged only"}


def apply_curated_commons(dataset: dict, sidecar: dict) -> dict:
    """Atomic in-memory merge; existing primary venue facts/status never change."""
    if sidecar.get("schema_version") != 1 or sidecar.get("kind") != "curated_commons_assignments":
        raise ValueError("Unsupported curated media sidecar")
    result = deepcopy(dataset)
    by_id = {poi["id"]: poi for poi in result["pois"]}
    for assignment in sidecar.get("assignments", []):
        poi = by_id.get(assignment.get("poi_id"))
        if poi is None or target_fingerprint(poi) != assignment.get("target_fingerprint"):
            raise ValueError("Curated image target identity changed")
        photo = deepcopy(assignment["photo"])
        if (not all(photo.get(key) for key in ("source_url", "license", "license_url", "author", "observed_at"))
                or not photo["source_url"].startswith("https://commons.wikimedia.org/wiki/File:")):
            raise ValueError("Unattributed image in curated expansion")
        acquired(photo["observed_at"])
        known = {p["source_url"] for p in poi.get("photos", [])}
        if photo["source_url"] not in known:
            poi.setdefault("photos", []).append(photo)
        if assignment.get("preferred_cover") is True:
            poi["photos"].sort(key=lambda item: item["source_url"] != photo["source_url"])
        poi["image"] = poi["photos"][0]["url"]
        evidence = poi.setdefault("media_identity_evidence", [])
        proof = {key: deepcopy(assignment[key]) for key in ("identity", "source_metadata", "source_description_sha256")}
        proof["source_url"] = photo["source_url"]
        if proof not in evidence:
            evidence.append(proof)
    return result


def cache_photos(sidecar: dict, directory: Path, *, client=None) -> dict:
    """Download only licensed, compiled Commons thumbnails, without publishing."""
    from PIL import Image
    result = deepcopy(sidecar)
    directory.mkdir(parents=True, exist_ok=True)
    stop = directory / "download-stop.json"
    if stop.exists():
        raise ValueError("A prior asset request stopped; inspect evidence before more requests")
    manifest_path = directory / "asset-manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    if not isinstance(manifest, dict):
        raise ValueError("Invalid retained asset manifest")

    def verify(content):
        if len(content) > MAX_RESPONSE:
            raise ValueError("Asset exceeds bounded thumbnail size")
        with Image.open(io.BytesIO(content)) as picture:
            if picture.format not in {"JPEG", "PNG", "WEBP"} or min(picture.size) < 160 or picture.width * picture.height > 20_000_000:
                raise ValueError("Invalid photographic thumbnail")
            extension = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[picture.format]
            picture.verify()
        return extension
    owns = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(25, connect=5), follow_redirects=False,
        trust_env=False, headers={"User-Agent": USER_AGENT})
    downloaded = {}
    try:
        for assignment in result["assignments"]:
            photo = assignment["photo"]
            remote = photo.get("remote_thumbnail_url") or photo["thumbnail_url"]
            parsed = urlsplit(remote)
            if parsed.scheme != "https" or parsed.hostname not in {"upload.wikimedia.org", "thumb.wikimedia.org"} or parsed.username or parsed.password or parsed.port not in {None, 443}:
                raise ValueError("Only public HTTPS Commons asset hosts are accepted")
            key = hashlib.sha256(photo["source_url"].encode()).hexdigest()[:20]
            existing = list(directory.glob(key + ".*"))
            if len(existing) > 1:
                raise ValueError("Ambiguous cached source asset")
            if remote in downloaded:
                path, content = downloaded[remote]
            elif existing:
                path = existing[0]
                content = path.read_bytes()
                proof = manifest.get(photo["source_url"], {})
                expected_sha = photo.get("asset_sha256") or proof.get("sha256")
                if (not expected_sha or hashlib.sha256(content).hexdigest() != expected_sha
                        or (photo.get("asset_sha256") and proof.get("sha256") and photo["asset_sha256"] != proof["sha256"])
                        or (proof and (proof.get("filename") != path.name or proof.get("remote_thumbnail_url") != remote))):
                    raise ValueError("Cached asset differs from retained source acquisition")
            else:
                status = None
                try:
                    with client.stream("GET", remote) as response:
                        status = response.status_code
                        if status != 200 or not response.headers.get("content-type", "").startswith("image/"):
                            raise ValueError("Asset source unavailable or not an image")
                        body = bytearray()
                        for part in response.iter_bytes():
                            body.extend(part)
                            if len(body) > MAX_RESPONSE:
                                raise ValueError("Asset exceeds bounded thumbnail size")
                        content = bytes(body)
                    extension = verify(content)
                    path = directory / (key + extension)
                    # A source file is never replaced after it has been acquired.
                    with path.open("xb") as handle:
                        handle.write(content)
                    manifest[photo["source_url"]] = {"filename": path.name, "sha256": hashlib.sha256(content).hexdigest(),
                        "remote_thumbnail_url": remote, "observed_at": datetime.now(timezone.utc).isoformat()}
                    atomic_write_json(manifest_path, manifest)
                    time.sleep(1)
                except (httpx.HTTPError, ValueError, OSError, Image.DecompressionBombError):
                    atomic_write_json(stop, {"source_url": photo["source_url"], "observed_at": datetime.now(timezone.utc).isoformat(),
                        "http_status": status, "decision": "stop_without_retry"})
                    raise
            # Decode cached files too; a partial/corrupt file is never accepted.
            extension = verify(content)
            if path.suffix != extension:
                raise ValueError("Cached image format differs from its asset extension")
            downloaded[remote] = path, content
            photo.setdefault("original_url", photo["url"])
            photo["remote_thumbnail_url"] = remote
            photo["url"] = photo["thumbnail_url"] = "/photos/" + path.name
            photo["asset_sha256"] = hashlib.sha256(content).hexdigest()
    finally:
        if owns:
            client.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/pois.json")
    parser.add_argument("--seeds", type=Path, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--collect", action="store_true", help="Acquire bounded public metadata; omit for offline replay")
    parser.add_argument("--download", action="store_true", help="Cache compiled licensed thumbnails into the staging directory")
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text())
    seeds = validate_seeds(json.loads(args.seeds.read_text()), dataset)
    if args.collect:
        collect_metadata(seeds, args.staging / "source-captures")
    sidecar = compile_sidecar(dataset, seeds, load_captures(args.staging / "source-captures"))
    if args.download:
        sidecar = cache_photos(sidecar, args.staging / "photos")
    atomic_write_json(args.staging / "curated-commons-sidecar.json", sidecar)
    print(json.dumps({"staged_assignments": len(sidecar["assignments"]), "held": len(sidecar["held"])}))


if __name__ == "__main__":
    main()
