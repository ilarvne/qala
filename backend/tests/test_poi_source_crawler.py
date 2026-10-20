"""Crawler security and evidence identity boundaries; no external requests."""
import base64
import json
import socket
from pathlib import Path

import httpx
import pytest

from scripts.poi_source_crawler import (CrawlRejected, SourceCrawler, extract_source_metadata,
                                        public_target, reusable_license)
from scripts.discover_poi_media import apply_verified_media_patches, physical_candidate, resolve_entities
from scripts.enrich_poi_media import canonical_file_title, place_photo_title


def resolver(address):
    return lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://user:password@example.com/",
                                      "http://localhost/", "http://metadata.google.internal/",
                                      "https://example.com:8080/", "http://example.local/"])
def test_only_public_http_urls(url):
    with pytest.raises(CrawlRejected):
        public_target(url, resolver("8.8.8.8"))


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "fc00::1"])
def test_non_public_dns_answers_are_rejected(address):
    with pytest.raises(CrawlRejected):
        public_target("https://operator.example/", resolver(address))


def test_actual_requests_pin_public_ip_and_keep_tls_hostname(tmp_path):
    requests = []
    def handler(request):
        requests.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /", headers={"content-type": "text/plain"})
        return httpx.Response(200, text="<html></html>", headers={"content-type": "text/html"})
    crawler = SourceCrawler(tmp_path, resolver=resolver("8.8.8.8"), transport=httpx.MockTransport(handler), min_delay=0)
    page = crawler.fetch_html("https://operator.example/branch")
    assert len(requests) == 2
    assert all(r.url.host == "8.8.8.8" for r in requests)
    assert all(r.headers["Host"] == "operator.example" for r in requests)
    assert all(r.extensions["sni_hostname"] == "operator.example" for r in requests)
    assert page["final_url"] == "https://operator.example/branch"
    assert crawler.fetch_html("https://operator.example/branch")["cache_hit"] is True
    assert len(requests) == 2


def test_disallowed_robots_never_requests_operator_page(tmp_path):
    requests = []
    def handler(request):
        requests.append(request.url.path)
        return httpx.Response(200, text="User-agent: *\nDisallow: /", headers={"content-type": "text/plain"})
    crawler = SourceCrawler(tmp_path, resolver=resolver("8.8.8.8"), transport=httpx.MockTransport(handler), min_delay=0)
    with pytest.raises(CrawlRejected, match="robots"):
        crawler.fetch_html("https://operator.example/private")
    assert requests == ["/robots.txt"]


def test_redirect_to_private_network_is_blocked_before_connection(tmp_path):
    requests = []
    def dns(host, *args, **kwargs):
        return resolver("127.0.0.1" if host == "internal.example" else "8.8.8.8")()
    def handler(request):
        requests.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(302, headers={"location": "https://internal.example/admin"})
    crawler = SourceCrawler(tmp_path, resolver=dns, transport=httpx.MockTransport(handler), min_delay=0)
    with pytest.raises(CrawlRejected, match="Non-public DNS"):
        crawler.fetch_html("https://operator.example/branch")
    assert requests == ["/robots.txt", "/branch"]


def test_decompressed_size_limit_is_enforced(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, content=b"x" * 200, headers={"content-type": "text/html"})
    crawler = SourceCrawler(tmp_path, max_bytes=100, resolver=resolver("8.8.8.8"), transport=httpx.MockTransport(handler), min_delay=0)
    with pytest.raises(CrawlRejected, match="byte cap"):
        crawler.fetch_html("https://operator.example/")


def page_for(node, *, og=True):
    html = ('<meta property="og:image" content="/generic-brand.jpg">' if og else "")
    html += '<script type="application/ld+json">' + json.dumps(node) + '</script>'
    return {"source_url": "https://operator.example/branch", "final_url": "https://operator.example/branch",
            "observed_at": "2026-10-20T00:00:00Z", "sha256": "fixture", "html_b64": base64.b64encode(html.encode()).decode()}


POI = {"id": "osm-node-1", "name": "Exact café", "lat": 51.1, "lon": 71.4}


def test_open_graph_and_unlicensed_operator_photos_are_not_exported():
    node = {"@type": "CafeOrCoffeeShop", "name": "Exact café", "geo": {"latitude": 51.1, "longitude": 71.4}, "image": "https://operator.example/real.jpg"}
    result = extract_source_metadata(POI, page_for(node))
    assert result["identity_verified"]
    assert len(result["images"]) == 2
    assert result["reusable_photos"] == []
    assert result["images"][0]["identity_verified"] is False


def test_wrong_branch_does_not_gain_photo_or_rating_from_shared_brand():
    node = {"name": "Exact café", "geo": {"latitude": 51.2, "longitude": 71.4},
            "image": {"url": "/photo.jpg", "license": "https://creativecommons.org/licenses/by/4.0/", "author": "Photographer"},
            "aggregateRating": {"ratingValue": 5, "ratingCount": 900}}
    result = extract_source_metadata(POI, page_for(node))
    assert result["identity_verified"] is False
    assert result["reusable_photos"] == [] and result["ratings"] == []


def test_explicit_license_author_and_branch_evidence_are_preserved():
    node = {"name": "Exact café", "geo": {"latitude": 51.1, "longitude": 71.4},
            "image": {"contentUrl": "/photo.jpg", "license": "https://creativecommons.org/licenses/by-sa/4.0/", "creator": {"name": "Photographer"}},
            "aggregateRating": {"ratingValue": 4.8, "ratingCount": 12}}
    result = extract_source_metadata(POI, page_for(node))
    assert result["reusable_photos"][0]["author"] == "Photographer"
    assert result["reusable_photos"][0]["license"] == "CC BY-SA 4.0"
    assert result["reusable_photos"][0]["identity_evidence"]["distance_m"] == 0
    assert result["reviews"] == []  # self-published score is only source metadata


def entity(qid="Q1", name="Exact café", lat=51.1, lon=71.4, cls="Q41176"):
    return {"id": qid, "labels": {"en": {"value": name}}, "aliases": {}, "claims": {
        "P625": [{"mainsnak": {"datavalue": {"value": {"latitude": lat, "longitude": lon, "precision": 0.00001, "globe": "http://www.wikidata.org/entity/Q2"}}}}],
        "P31": [{"mainsnak": {"datavalue": {"value": {"id": cls}}}}]}}


def test_name_and_coordinates_both_required_for_wikidata_reconciliation():
    assert resolve_entities([POI], {"Q1": entity()})[0] == {"osm-node-1": "Q1"}
    assert resolve_entities([POI], {"Q1": entity(name="Nearby place")})[0] == {}
    assert resolve_entities([POI], {"Q1": entity(lat=51.2)})[0] == {}
    linked = {**POI, "wikidata": "Q1"}
    assert resolve_entities([linked], {"Q1": entity(lat=51.2)})[0] == {}


def test_physical_candidate_whitelist_excludes_companies_and_jurisdictions():
    assert physical_candidate("Q1", entity(cls="Q4830453"), [], "now", [50, 70, 52, 72]) is None
    assert physical_candidate("Q1", entity(), [], "now", [10, 10, 20, 20]) is None
    row = physical_candidate("Q1", entity(), [], "now", [50, 70, 52, 72])
    assert row["id"] == "wikidata-Q1" and row["hours"] is None
    assert row["source"]["license"] == "CC0" and row["photos"] == []
    assert row["indoor"] is None and row["wheelchair"] == "unknown"


def test_boulevard_and_architectural_structure_are_physical_but_a_generic_street_is_not_a_destination():
    for cls, kind in (("Q54114", "boulevard"), ("Q811979", "architectural_structure")):
        row = physical_candidate("Q1", entity(cls=cls), [], "original-acquisition", [50, 70, 52, 72])
        assert row["poi_type"] == kind and row["hours"] is None
        assert row["source"]["collected_at"] == "original-acquisition"
    assert physical_candidate("Q1", entity(cls="Q79007"), [], "now", [50, 70, 52, 72]) is None


def test_retained_media_patch_cannot_move_to_a_reused_or_relocated_id():
    import copy
    data = {"metadata": {}, "pois": [{**POI, "wikidata": None}]}
    sidecar = {"pois": {POI["id"]: {"wikidata": "Q1", "photos": [], "image": None}},
               "target_coordinates": {POI["id"]: {"lat": POI["lat"], "lon": POI["lon"]}},
               "identity_audit": [{"poi_id": POI["id"], "qid": "Q1", "accepted": True}]}
    apply_verified_media_patches(data, sidecar)
    assert data["pois"][0]["wikidata"] == "Q1"
    relocated = copy.deepcopy(data)
    relocated["pois"][0]["lat"] += 0.01
    with pytest.raises(ValueError, match="coordinates"):
        apply_verified_media_patches(relocated, sidecar)
    rejected = copy.deepcopy(sidecar)
    rejected["identity_audit"] = []
    with pytest.raises(ValueError, match="reconciliation"):
        apply_verified_media_patches(data, rejected)


def test_mediawiki_normalization_cannot_bypass_visual_curation():
    assert canonical_file_title("File:Abu_Dhabi_Plaza_10.2015.jpg") == "File:Abu Dhabi Plaza 10.2015.jpg"
    assert not place_photo_title("File:Stamps of Kazakhstan, 2012-32.jpg")
    assert not place_photo_title("File:ISS023-E-42356 - View of Kazakhstan (cropped).jpg")
    assert not place_photo_title("File:Dmitry Medvedev in Kazakhstan 22 May 2008-3.jpg")


def test_license_name_cannot_be_forged_in_query_or_non_reusable_variant():
    assert reusable_license("https://creativecommons.org/licenses/by/4.0/") == "CC BY 4.0"
    assert reusable_license("https://creativecommons.org/?redirect=creativecommons.org/licenses/by/4.0/") is None
    assert reusable_license("https://creativecommons.org/licenses/by-nc/4.0/") is None
    assert reusable_license("https://creativecommons.org.evil.example/licenses/by/4.0/") is None


def test_coarse_or_demolished_entities_are_not_new_visitable_landmarks():
    coarse = entity()
    coarse["claims"]["P625"][0]["mainsnak"]["datavalue"]["value"]["precision"] = 0.014
    assert physical_candidate("Q1", coarse, [], "now", [50, 70, 52, 72]) is None
    dissolved = entity()
    dissolved["claims"]["P576"] = [{"mainsnak": {"datavalue": {"value": {"time": "+2000-01-01T00:00:00Z"}}}}]
    assert physical_candidate("Q1", dissolved, [], "now", [50, 70, 52, 72]) is None
