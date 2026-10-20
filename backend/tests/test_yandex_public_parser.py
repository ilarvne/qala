"""Public-card parsing must not leak reviews or confuse map/branch identities."""
import json

from scripts.providers.yandex import organization_id, parse_html


def page(business=None):
    business = business or {
        "type": "business", "id": "123", "uri": "ymapsbm1://org?oid=123",
        "title": "Test museum", "address": "Astana, test street 1", "coordinates": [71.4, 51.1],
        "ratingData": {"ratingValue": 4.7, "ratingCount": 130, "reviewCount": 48},
        "photos": {"items": [{"urlTemplate": "https://avatars.mds.yandex.net/get-altay/1/photo/%s"}]},
        "reviewResults": [{"author": "Do not export", "text": "Private review body"}],
        "requestId": "secret-request-id",
    }
    value = {"config": {"latitude": 55.75, "longitude": 37.6}, "stack": [{"results": {"items": [business]}}]}
    return '<script type="application/json" class="state-view">' + json.dumps(value) + '</script>'


URL = "https://yandex.com/maps/org/test_museum/123/"


def test_exact_organization_metadata_without_user_or_session_content():
    result = parse_html(page(), URL)[0]
    assert (result["provider_id"], result["lat"], result["lon"]) == ("123", 51.1, 71.4)
    assert (result["rating"], result["rating_count"], result["review_count"]) == (4.7, 130, 48)
    assert result["photo_source_links"] == ["https://avatars.mds.yandex.net/get-altay/1/photo/orig"]
    assert result["import_policy"] == "evaluation_only"
    serialized = json.dumps(result)
    assert all(secret not in serialized for secret in ["Private review body", "Do not export", "secret-request-id"])


def test_wrong_branch_or_missing_matching_uri_is_rejected():
    assert parse_html(page(), URL.replace("/123/", "/124/")) == []
    assert parse_html(page({"type": "business", "id": "123", "title": "Test"}), URL) == []


def test_viewport_coordinates_do_not_become_place_coordinates():
    result = parse_html(page({"type": "business", "id": "123", "uri": "ymapsbm1://org?oid=123", "title": "Test"}), URL)[0]
    assert result["lat"] is None and result["lon"] is None


def test_invalid_numbers_are_unknown_and_image_queries_are_not_exported():
    result = parse_html(page({"type": "business", "id": "123", "uri": "ymapsbm1://org?oid=123", "title": "Test",
                              "coordinates": [float("inf"), 51.1], "ratingData": {"ratingValue": 8, "ratingCount": True, "reviewCount": -2},
                              "photos": {"items": [{"urlTemplate": "https://avatars.mds.yandex.net/get-altay/1/a/%s?token=secret"}]}}), URL)[0]
    assert result["lat"] is None and result["lon"] is None
    assert result["rating"] is None and result["rating_count"] is None and result["review_count"] is None
    assert result["photo_source_links"] == []


def test_query_tokens_removed_and_public_organization_url_required():
    result = parse_html(page(), URL + "?session=never-export#fragment")[0]
    assert result["source_url"] == URL
    assert parse_html(page(), "https://evil.example/maps/org/test/123/") == []
    assert parse_html(page(), "https://user:pass@yandex.com/maps/org/test/123/") == []
    assert organization_id("https://yandex.com:444/maps/org/test/123/") is None
    assert organization_id("https://yandex.com:invalid/maps/org/test/123/") is None
    assert organization_id("https://[broken/maps/org/test/123/") is None
    assert parse_html(page(), URL + "reviews/")[0]["review_source_links"] == [URL + "reviews/"]


def test_malformed_or_oversize_public_state_is_rejected():
    assert parse_html('<script type="application/json" class="state-view">bad</script>', URL) == []
    assert parse_html("x" * 2_500_001, URL) == []
    assert parse_html('<script>window.app = ' + json.dumps({"title": "Test"}) + '</script>', URL) == []


def test_cached_html_reparse_preserves_original_acquisition_time():
    acquired = "2024-01-02T03:04:05+06:00"
    original = parse_html(page(), URL, observed_at=acquired)[0]
    replay = parse_html(page(), URL, observed_at=acquired)[0]
    assert original["observed_at"] == replay["observed_at"] == acquired
    assert not any("acquisition time is unknown" in warning for warning in replay["warnings"])


def test_cached_html_without_acquisition_metadata_remains_unknown():
    row = parse_html(page(), URL)[0]
    assert row["observed_at"] is None
    assert any("Original acquisition time is unknown" in warning for warning in row["warnings"])
