#!/usr/bin/env python3
"""Bounded, robots-aware collection of source metadata from POI operator pages.

The crawler does not turn an Open Graph image into a reusable photograph. Only
an identity-matched ImageObject with an explicit supported licence can be
exported as media. Unlicensed image/review candidates remain source links.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import math
import re
import socket
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "QalaResearch/3.0 (+https://www.openstreetmap.org/relation/3087155; POI source metadata)"
BLOCKED_HOSTS = {"metadata.google.internal", "localhost", "localhost.localdomain"}


class CrawlRejected(ValueError):
    pass


def public_target(url: str, resolver=socket.getaddrinfo) -> tuple[str, str, int]:
    """Validate URL and every DNS answer; return the public address to pin.

    Pinning the validated IP in the actual request avoids a DNS rebinding race.
    TLS still verifies the original hostname through its SNI extension.
    """
    parsed = urlsplit(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise CrawlRejected("Only credential-free HTTP(S) source URLs are allowed")
    host = parsed.hostname.encode("idna").decode().lower().rstrip(".")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise CrawlRejected("Invalid port") from exc
    if port not in {80, 443} or host in BLOCKED_HOSTS or host.endswith((".local", ".internal", ".localhost")):
        raise CrawlRejected("Non-public host or port")
    try:
        addresses = sorted({item[4][0] for item in resolver(host, port, type=socket.SOCK_STREAM)})
    except OSError as exc:
        raise CrawlRejected("DNS resolution failed") from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise CrawlRejected("Non-public DNS address")
    return host, addresses[0], port


class SourceCrawler:
    def __init__(self, cache_dir: Path, *, timeout: float = 15, max_bytes: int = 1_500_000,
                 min_delay: float = 1.0, resolver=socket.getaddrinfo, transport=None):
        self.cache_dir, self.timeout, self.max_bytes = cache_dir, timeout, max_bytes
        self.min_delay, self.resolver, self.transport = min_delay, resolver, transport
        self._robots: dict[str, RobotFileParser | None] = {}
        self._robots_lock = threading.Lock()
        self._rate_lock = threading.Lock()
        self._last: dict[str, float] = {}
        self.request_count = 0

    def _wait(self, host: str, delay: float = 0) -> None:
        with self._rate_lock:
            now = time.monotonic()
            wait = max(self.min_delay, delay) - (now - self._last.get(host, 0))
            if wait > 0:
                time.sleep(wait)
            self._last[host] = time.monotonic()

    def _fetch(self, url: str, *, robots: bool = False) -> tuple[bytes, str, int, str]:
        """Manually validate each redirect, cap decompressed bytes, bound retries."""
        current = url
        for redirect in range(5):
            host, address, port = public_target(current, self.resolver)
            if not robots and not self.allowed(current):
                raise CrawlRejected("robots.txt disallows this path or could not be verified")
            parsed = urlsplit(current)
            bracketed = "[" + address + "]" if ":" in address else address
            default_port = 443 if parsed.scheme == "https" else 80
            pinned = urlunsplit((parsed.scheme, bracketed + (":" + str(port) if port != default_port else ""), parsed.path or "/", parsed.query, ""))
            result = None
            for attempt in range(2):
                self._wait(host)
                # One pool per pinned request: hosts sharing an IP must never
                # reuse a TLS connection authenticated for a different host.
                with httpx.Client(timeout=self.timeout, follow_redirects=False,
                                  trust_env=False, transport=self.transport) as client:
                    with client.stream("GET", pinned, headers={"Host": host, "User-Agent": USER_AGENT,
                                                              "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9"},
                                       extensions={"sni_hostname": host}) as response:
                        self.request_count += 1
                        if response.status_code in {429, 503} and attempt == 0:
                            retry = response.headers.get("Retry-After", "1")
                            try:
                                pause = float(retry)
                            except ValueError:
                                pause = 2
                            if pause > 10:
                                raise CrawlRejected("Provider requested a longer retry; defer source")
                            time.sleep(max(1, pause))
                            continue
                        if response.is_redirect:
                            destination = response.headers.get("location")
                            if not destination:
                                raise CrawlRejected("Redirect without location")
                            current = urljoin(current, destination)
                            result = "redirect"
                            break
                        size = response.headers.get("content-length")
                        if size and size.isdigit() and int(size) > self.max_bytes:
                            raise CrawlRejected("Source exceeds byte cap")
                        chunks, total = [], 0
                        for chunk in response.iter_bytes():
                            total += len(chunk)
                            if total > self.max_bytes:
                                raise CrawlRejected("Source exceeds decompressed byte cap")
                            chunks.append(chunk)
                        return b"".join(chunks), current, response.status_code, response.headers.get("content-type", "")
            if result != "redirect":
                raise CrawlRejected("Bounded retries exhausted")
        raise CrawlRejected("Too many redirects")

    def allowed(self, url: str) -> bool:
        parsed = urlsplit(url)
        origin = parsed.scheme + "://" + parsed.netloc
        # Serialise initial robots loads so multiple pages on a host do not
        # race into a burst of duplicate robots requests.
        with self._robots_lock:
            if origin not in self._robots:
                try:
                    body, _, status, _ = self._fetch(origin + "/robots.txt", robots=True)
                    parser = RobotFileParser(origin + "/robots.txt")
                    if status == 404:
                        parser.parse([])
                    elif status == 200:
                        parser.parse(body.decode("utf-8", errors="replace").splitlines())
                    else:
                        self._robots[origin] = None
                        return False
                    self._robots[origin] = parser
                except (CrawlRejected, httpx.HTTPError):
                    self._robots[origin] = None
            parser = self._robots[origin]
        if parser is None or not parser.can_fetch(USER_AGENT, url):
            return False
        crawl_delay = parser.crawl_delay(USER_AGENT) or parser.crawl_delay("*") or 0
        if crawl_delay > 10:
            return False  # defer rather than violate a long crawl delay
        if crawl_delay:
            self._wait(parsed.hostname or "", crawl_delay)
        return True

    def fetch_html(self, url: str) -> dict:
        key = hashlib.sha256(url.encode()).hexdigest()
        file = self.cache_dir / (key + ".json")
        if file.exists():
            cached = json.loads(file.read_text())
            # Freshness is explicit; old metadata is never silently refreshed.
            if time.time() - file.stat().st_mtime < 24 * 3600:
                return {**cached, "cache_hit": True}
        body, final, status, kind = self._fetch(url)
        if status != 200:
            raise CrawlRejected("Source HTTP " + str(status))
        if "html" not in kind.lower():
            raise CrawlRejected("Source is not HTML")
        payload = {"source_url": url, "final_url": final, "observed_at": datetime.now(timezone.utc).isoformat(),
                   "sha256": hashlib.sha256(body).hexdigest(), "html_b64": base64.b64encode(body).decode(), "cache_hit": False}
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(payload))
        file.chmod(0o600)
        return payload


class MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta, self.jsonld, self._script, self._parts = {}, [], False, []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "meta":
            key = values.get("property") or values.get("name")
            if key and values.get("content"):
                self.meta[key.lower()] = values["content"]
        if tag == "script" and values.get("type", "").split(";")[0].lower() == "application/ld+json":
            self._script, self._parts = True, []

    def handle_data(self, data):
        if self._script:
            self._parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._script:
            self._script = False
            try:
                self.jsonld.append(json.loads("".join(self._parts)))
            except (ValueError, RecursionError):
                pass


def normalize(value: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", "".join(c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c))))


def distance_m(a: float, b: float, c: float, d: float) -> float:
    x, y = math.radians(a), math.radians(c)
    h = math.sin((y - x) / 2) ** 2 + math.cos(x) * math.cos(y) * math.sin(math.radians(d - b) / 2) ** 2
    return 12742000 * math.asin(math.sqrt(min(1, h)))


def reusable_license(value) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"https", "http"} or parsed.netloc.removeprefix("www.") != "creativecommons.org" or parsed.query or parsed.fragment:
        return None
    match = re.fullmatch(r"/licenses/(by|by-sa)/(1\.0|2\.0|2\.5|3\.0|4\.0)/?", parsed.path)
    if match:
        return "CC BY-SA " + match[2] if match[1] == "by-sa" else "CC BY " + match[2]
    if re.fullmatch(r"/publicdomain/zero/1\.0/?", parsed.path):
        return "CC0"
    if re.fullmatch(r"/publicdomain/mark/1\.0/?", parsed.path):
        return "Public domain"
    return None


def jsonld_nodes(value, depth: int = 0):
    if depth > 8:
        return
    if isinstance(value, dict):
        yield value
        for item in value.values():
            if isinstance(item, (dict, list)):
                yield from jsonld_nodes(item, depth + 1)
    elif isinstance(value, list):
        for item in value[:200]:
            yield from jsonld_nodes(item, depth + 1)


def extract_source_metadata(poi: dict, page: dict) -> dict:
    parser = MetadataParser()
    parser.feed(base64.b64decode(page["html_b64"]).decode("utf-8", errors="replace"))
    source = {key: page[key] for key in ("source_url", "final_url", "observed_at", "sha256")}
    source.update(poi_id=poi["id"], poi_name=poi["name"], provider="POI operator website",
                  images=[], ratings=[], reviews=[], reusable_photos=[], identity_verified=False)
    # Open Graph is a discovery hint only; it commonly points to a brand logo,
    # generic hotel/restaurant image or a different branch.
    if parser.meta.get("og:image"):
        source["images"].append({"url": urljoin(page["final_url"], parser.meta["og:image"]),
                                 "discovery": "Open Graph", "reuse_permission": "unknown", "identity_verified": False})
    for doc in parser.jsonld:
        for node in jsonld_nodes(doc):
            geo = node.get("geo")
            if not isinstance(geo, dict) or not isinstance(node.get("name"), str):
                continue
            try:
                lat, lon = float(geo["latitude"]), float(geo["longitude"])
                if not math.isfinite(lat + lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    continue
                distance = distance_m(poi["lat"], poi["lon"], lat, lon)
            except (KeyError, ValueError, TypeError):
                continue
            names = [poi["name"], *[v for k, v in poi.get("raw_tags", {}).items() if k.startswith("name:")]]
            if distance > 150 or normalize(node["name"]) not in {normalize(n) for n in names}:
                continue
            source["identity_verified"] = True
            source["identity_evidence"] = {"method": "exact normalized name and branch coordinates", "distance_m": round(distance, 1), "name": node["name"]}
            images = node.get("image", [])
            for item in images if isinstance(images, list) else [images]:
                image = item if isinstance(item, dict) else {"url": item}
                url = image.get("contentUrl") or image.get("url")
                if not isinstance(url, str):
                    continue
                url = urljoin(page["final_url"], url)
                license_url = image.get("license") or node.get("license")
                license_name = reusable_license(license_url)
                candidate = {"url": url, "discovery": "JSON-LD", "identity_verified": True,
                             "reuse_permission": "explicit open license" if license_name else "unknown", "license_url": license_url}
                source["images"].append(candidate)
                author = image.get("creator") or image.get("author") or image.get("copyrightHolder")
                if isinstance(author, dict):
                    author = author.get("name")
                if license_name and (author or license_name in {"CC0", "Public domain"}):
                    source["reusable_photos"].append({"url": url, "thumbnail_url": url, "source_url": page["final_url"],
                        "title": node["name"], "provider": "POI operator website", "license": license_name, "license_url": license_url,
                        "author": author or "Public-domain contributor", "attribution": f"{author or 'Public domain'} · {license_name}",
                        "observed_at": page["observed_at"], "identity_evidence": source["identity_evidence"]})
            # Self-published ratings are retained as source metadata, never
            # merged into independent user-review ratings without their terms.
            aggregate = node.get("aggregateRating")
            if isinstance(aggregate, dict):
                source["ratings"].append({key: aggregate[key] for key in ("ratingValue", "bestRating", "worstRating", "ratingCount", "reviewCount") if key in aggregate})
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/pois.json")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/media-upgrade-staging/operator-source-audit.json")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text())
    # Visit each exact operator URL once, then assess every associated branch.
    grouped = {}
    for poi in dataset["pois"]:
        url = poi.get("website")
        if isinstance(url, str) and urlsplit(url).scheme in {"http", "https"}:
            grouped.setdefault(url, []).append(poi)
    # Distinct branch pages before shared brand homepages; no social network
    # scraping or map-provider review scraping.
    denied = {"instagram.com", "www.instagram.com", "facebook.com", "www.facebook.com", "2gis.kz", "google.com", "yandex.kz", "yandex.ru"}
    selected = [(url, rows) for url, rows in grouped.items() if urlsplit(url).hostname not in denied]
    selected.sort(key=lambda item: (len(item[1]), -len(urlsplit(item[0]).path), item[0]))
    crawler = SourceCrawler(ROOT / ".local/poi-crawler-cache")
    def collect(item):
        url, rows = item
        try:
            page = crawler.fetch_html(url)
            return {"url": url, "status": "collected", "sources": [extract_source_metadata(p, page) for p in rows]}
        except (CrawlRejected, httpx.HTTPError, ValueError) as exc:
            return {"url": url, "status": "deferred", "reason": type(exc).__name__ + ": " + str(exc)[:160], "poi_ids": [p["id"] for p in rows]}
    with ThreadPoolExecutor(max_workers=min(6, max(1, args.workers))) as pool:
        records = list(pool.map(collect, selected[:max(0, args.limit)]))
    report = {"schema_version": 1, "observed_at": datetime.now(timezone.utc).isoformat(),
              "source_dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(), "url_candidates": len(selected),
              "urls_attempted": len(records), "network_requests": crawler.request_count,
              "urls_collected": sum(r["status"] == "collected" for r in records), "records": records,
              "policy": "Robots-aware, 1 request/second/host minimum, public-IP-pinned DNS, bounded redirects/retries/bytes; unlicensed media only linked, never redistributed; self-published ratings not treated as independent reviews."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "records"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
