"""Provider adapters never weaken source, privacy or upload boundaries."""
import asyncio
import json
import io
import shutil
import subprocess
import wave

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import alemplus
from backend.main import app


def provider_client(monkeypatch, result, capture):
    class Client:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, **kwargs):
            capture.append((url, kwargs))
            return result
    monkeypatch.setattr(alemplus.httpx, "AsyncClient", Client)


def test_valid_alem_is_selected_instead_of_unrelated_openai_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "invalid-fixture")
    monkeypatch.setenv("ALEMPLUS_API_KEY", "alem-fixture")
    configuration = alemplus.chat_configuration()
    assert configuration["provider"] == "AlemPlus" and configuration["base_url"] == "https://llm.alem.ai/v1"
    assert configuration["api_key"] == "alem-fixture"


@pytest.mark.parametrize("results", [[{"index": 99, "relevance_score": .9}], [{"index": 0, "relevance_score": float("nan")}], [{"index": 0, "relevance_score": .9}, {"index": 0, "relevance_score": .8}]])
def test_malformed_rerank_cannot_invent_or_duplicate_pois(monkeypatch, results):
    monkeypatch.setenv("ALEMPLUS_RERANK_KEY", "fixture")
    capture = []
    # JSONResponse rejects NaN; HTTP transport bytes remain untrusted input.
    provider_client(monkeypatch, httpx.Response(200, content=json.dumps({"results": results})), capture)
    original = [{"id": "trusted", "name": "Cafe", "category": "cafe", "description": "Public cafe", "retrieval_score": .5, "distance_m": 10}]
    ranked, report = asyncio.run(alemplus.rerank_candidates(original, ["coffee"]))
    assert ranked == original and report["applied"] is False
    assert "source" not in ranked[0]


def test_valid_rerank_only_reorders_trusted_evidence_and_no_user_location_is_sent(monkeypatch):
    monkeypatch.setenv("ALEMPLUS_RERANK_KEY", "fixture")
    capture = []
    provider_client(monkeypatch, httpx.Response(200, json={"results": [{"index": 0, "relevance_score": .9}]}), capture)
    original = [{"id": "trusted", "name": "Cafe", "category": "cafe", "description": "Public cafe", "retrieval_score": .5, "distance_m": 10,
                 "lat": 51.1, "lon": 71.4, "source": {"url": "https://www.openstreetmap.org/node/1"}}]
    ranked, report = asyncio.run(alemplus.rerank_candidates(original, ["coffee"]))
    assert report["applied"] is True and ranked[0]["source"] == original[0]["source"]
    payload = capture[0][1]["json"]
    assert "51.1" not in json.dumps(payload) and "location" not in payload and "session_id" not in payload
    assert set(payload) == {"model", "query", "documents", "top_n"}


def test_kazakh_speech_uses_separate_model_key_and_server_response_is_sanitized(monkeypatch):
    monkeypatch.setenv("ALEMPLUS_STT_KK_KEY", "kk-fixture")
    capture = []
    provider_client(monkeypatch, httpx.Response(200, json={"text": "Кофе ішкім келеді"}), capture)
    result = asyncio.run(alemplus.transcribe_audio(b"fixture-audio", "dictation.mp3", "audio/mpeg", "kk"))
    assert result["model"] == "speech-to-text-kk" and result["language"] == "kk"
    assert capture[0][1]["data"] == {"model": "speech-to-text-kk"}
    assert capture[0][1]["headers"]["Authorization"] == "Bearer kk-fixture"
    provider_client(monkeypatch, httpx.Response(401, json={"error": "do not echo fixture-secret"}), capture)
    with pytest.raises(alemplus.ProviderUnavailable) as error:
        asyncio.run(alemplus.transcribe_audio(b"fixture-audio", "dictation.mp3", "audio/mpeg", "kk"))
    assert "fixture-secret" not in str(error.value) and "401" not in str(error.value)


def test_transcription_endpoint_rejects_wrong_type_and_oversize_before_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("QALA_MEMORY_PATH", str(tmp_path / "memory.sqlite3"))
    monkeypatch.setenv("QALA_EMBEDDINGS", "hash")
    calls = []
    async def transcribe(audio, filename, mime, language):
        calls.append((len(audio), filename, mime, language))
        return {"text": "Кофе", "language": language, "provider": "AlemPlus", "model": "speech-to-text-kk"}
    monkeypatch.setattr("backend.main.transcribe_audio", transcribe)
    with TestClient(app) as client:
        assert client.post("/api/voice/transcribe", files={"file": ("test.txt", b"text", "text/plain")}).status_code == 415
        assert client.post("/api/voice/transcribe", files={"file": ("test.wav", b"x" * (8 * 1024 * 1024 + 1), "audio/wav")}).status_code == 413
        assert calls == []
        response = client.post("/api/voice/transcribe", data={"language": "kk"}, files={"file": ("user-private-name.mp3", b"audio", "audio/mpeg")})
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert calls == [(5, "dictation.mp3", "audio/mpeg", "kk")]


@pytest.mark.parametrize("mime,container,codec,extra", [("audio/webm", "webm", "libopus", []), ("audio/ogg", "ogg", "libopus", []), ("audio/mp4", "mp4", "aac", ["-movflags", "frag_keyframe+empty_moov"])])
def test_actual_browser_containers_become_canonical_16k_mono_wav(mime, container, codec, extra):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg is an explicit browser-dictation runtime dependency")
    encoded = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "0.1", "-ac", "2", "-c:a", codec, *extra, "-f", container, "pipe:1"], capture_output=True, check=True).stdout
    normalized = asyncio.run(alemplus.normalize_browser_audio(encoded, mime))
    with wave.open(io.BytesIO(normalized), "rb") as wav:
        assert wav.getnchannels() == 1 and wav.getframerate() == 16000 and wav.getsampwidth() == 2
        assert 1000 <= wav.getnframes() <= 2200
        assert any(wav.readframes(wav.getnframes()))


def test_browser_transcription_forwards_normalized_wav_with_fixed_name(monkeypatch):
    monkeypatch.setenv("ALEMPLUS_STT_KEY", "fixture")
    capture = []
    async def normalize(audio, mime):
        assert audio == b"webm-audio" and mime == "audio/webm"
        return b"canonical-wav"
    monkeypatch.setattr(alemplus, "normalize_browser_audio", normalize)
    provider_client(monkeypatch, httpx.Response(200, json={"text": "Тест"}), capture)
    result = asyncio.run(alemplus.transcribe_audio(b"webm-audio", "private-name.webm", "audio/webm;codecs=opus", "ru"))
    assert result["text"] == "Тест"
    assert capture[0][1]["files"]["file"] == ("dictation.wav", b"canonical-wav", "audio/wav")


def test_conversion_timeout_kills_and_reaps_process_without_exposing_errors(monkeypatch):
    class Process:
        returncode = None
        killed = False
        reaped = False
        async def communicate(self, audio=None):
            self.reaped = self.killed
            return b"", None
        def kill(self):
            self.killed = True
            self.returncode = -9
    process, arguments = Process(), []
    async def create(*args, **kwargs):
        arguments.extend(args)
        return process
    async def timeout(awaitable, timeout):
        awaitable.close()
        raise TimeoutError("never echo fixture-secret")
    monkeypatch.setattr(alemplus.asyncio, "create_subprocess_exec", create)
    monkeypatch.setattr(alemplus.asyncio, "wait_for", timeout)
    with pytest.raises(alemplus.ProviderUnavailable) as error:
        asyncio.run(alemplus.normalize_browser_audio(b"audio", "audio/webm"))
    assert process.killed and process.reaped and "fixture-secret" not in str(error.value)
    assert arguments[arguments.index("-protocol_whitelist") + 1] == "pipe"
    assert arguments[arguments.index("-t") + 1] == "61"


def test_invalid_browser_audio_fails_before_any_provider_request(monkeypatch):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg is an explicit browser-dictation runtime dependency")
    monkeypatch.setenv("ALEMPLUS_STT_KEY", "fixture")
    capture = []
    provider_client(monkeypatch, httpx.Response(200, json={"text": "must not be used"}), capture)
    with pytest.raises(alemplus.ProviderUnavailable):
        asyncio.run(alemplus.transcribe_audio(b"not a WebM file", "dictation.webm", "audio/webm", "ru"))
    assert capture == []
