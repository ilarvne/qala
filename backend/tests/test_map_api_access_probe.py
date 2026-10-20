import json

import httpx
import pytest

from scripts.probe_map_api_access import configured_key, probe, KEY_NAMES


@pytest.mark.parametrize("provider", ["google", "2gis"])
@pytest.mark.parametrize("value", ["environment-fixture-key", ""])
def test_environment_secret_or_explicit_disable_wins_over_private_file(monkeypatch, tmp_path, provider, value):
    name = KEY_NAMES[provider]
    env_file = tmp_path / ".env"
    env_file.write_text(name + "=file-fixture-key\n")
    monkeypatch.setenv(name, value)
    assert configured_key(provider, env_file) == value
    monkeypatch.delenv(name)
    assert configured_key(provider, env_file) == "file-fixture-key"


@pytest.mark.parametrize("provider", ["google", "2gis"])
def test_no_network_without_explicit_live_or_missing_key(provider):
    def forbidden(request):
        pytest.fail("Configuration check attempted network")
    transport = httpx.MockTransport(forbidden)
    assert probe(provider, "not-a-real-key", transport=transport)["request_count"] == 0
    assert probe(provider, None, live=True, transport=transport)["status"] == "not_configured"


def test_google_owned_key_is_in_header_only_and_payload_not_retained():
    secret = "private-fixture-key"
    def respond(request):
        assert request.headers["X-Goog-Api-Key"] == secret
        assert secret not in str(request.url)
        assert "*" not in request.headers["X-Goog-FieldMask"]
        assert "places.reviews" in request.headers["X-Goog-FieldMask"]
        assert json.loads(request.content)["pageSize"] == 1
        return httpx.Response(200, json={"places": [{"id": "ChIJfixture", "rating": 4.6, "userRatingCount": 123,
                    "photos": [{"name": "private-photo-resource"}], "reviews": [{"text": {"text": "review body not retained"}}]}]})
    result = probe("google", secret, live=True, reviews=True, transport=httpx.MockTransport(respond))
    assert result["status"] == "live_verified" and result["request_count"] == 1
    assert result["fields_observed"] == {"rating": 1, "rating_count": 1, "photo_resources": 1, "review_samples": 1}
    encoded = json.dumps(result)
    assert all(value not in encoded for value in [secret, "private-photo-resource", "review body not retained"])


@pytest.mark.parametrize("status", [401, 403, 429, 302])
def test_denials_or_redirects_are_never_retried_or_followed(status):
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(status, headers={"Location": "https://unrelated.invalid/"}, text="untrusted provider message")
    result = probe("google", "private-fixture-key", live=True, transport=httpx.MockTransport(respond))
    assert len(requests) == 1 and result["http_status"] == status
    assert result["status"] != "live_verified"
    assert "untrusted provider message" not in json.dumps(result)


def test_2gis_http_200_with_meta_400_is_not_success_and_key_is_redacted():
    key = "private-fixture-key"
    def respond(request):
        assert request.url.params["key"] == key
        return httpx.Response(200, json={"meta": {"code": 400, "error": {"message": key}}})
    result = probe("2gis", key, live=True, transport=httpx.MockTransport(respond))
    assert result["status"] == "denied" and result["api_status"] == "META_400"
    assert key not in json.dumps(result)


def test_exception_with_credentialed_url_does_not_leak():
    key = "private-fixture-key"
    def fail(request):
        raise httpx.ConnectError(str(request.url), request=request)
    result = probe("2gis", key, live=True, transport=httpx.MockTransport(fail))
    assert result["status"] == "provider_unavailable" and key not in json.dumps(result)
