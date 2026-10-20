"""Conversation locale can differ from the strictly grounded planner locale."""
import json
from pathlib import Path
from typing import get_args
import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from backend.models import VoiceSessionRequest, RecommendRequest, SpeechRequest
from backend import main

ROOT = Path(__file__).resolve().parents[2]
LANGUAGES = json.loads((ROOT / "data/voice-languages.json").read_text())


def test_all_configured_conversation_languages_are_accepted_without_changing_planner_or_dictation_languages():
    codes = {item["code"] for item in LANGUAGES}
    assert len(codes) == 16
    assert codes == set(get_args(VoiceSessionRequest.model_fields["language"].annotation))
    for code in codes:
        assert VoiceSessionRequest(language=code).language == code
        if code not in {"en", "ru", "kk"}:
            with pytest.raises(ValidationError): RecommendRequest(language=code)
            with pytest.raises(ValidationError): SpeechRequest(text="Example", language=code)
    with pytest.raises(ValidationError): VoiceSessionRequest(language="unsupported")


def test_foreign_voice_locale_issues_only_a_private_session_url_and_does_not_start_audio(monkeypatch, tmp_path):
    received = []
    def transport(request):
        received.append(request)
        assert request.method == "GET"
        assert request.url.path == "/v1/convai/conversation/get-signed-url"
        assert request.headers["xi-api-key"] == "fixture-provider-key"
        return httpx.Response(200, json={"signed_url": "wss://api.elevenlabs.io/session?token=fixture-only"})
    async_client = httpx.AsyncClient
    monkeypatch.setenv("ELEVENLABS_API_KEY", "fixture-provider-key")
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", "fixture-agent")
    monkeypatch.setenv("QALA_MEMORY_PATH", str(tmp_path / "memory.sqlite3"))
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **_: async_client(transport=httpx.MockTransport(transport)))
    with TestClient(main.app) as client:
        result = client.post("/api/voice/session", json={"language": "fr"})
        assert result.status_code == 200
        assert result.headers["cache-control"] == "no-store"
        assert result.json()["language"] == "fr"
        assert client.post("/api/voice/session", json={"language": "unsupported"}).status_code == 422
        assert client.post("/api/recommend", json={"language": "fr"}).status_code == 422
    assert len(received) == 1
