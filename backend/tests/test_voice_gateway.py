import httpx
from fastapi.testclient import TestClient
from backend import voice_gateway


def test_gateway_exposes_only_the_voice_webhook():
    with TestClient(voice_gateway.app) as client:
        for path in ("/", "/docs", "/api/health", "/api/chat", "/api/memory/example"):
            assert client.get(path).status_code == 404


def test_gateway_rejects_large_and_non_json_inputs():
    with TestClient(voice_gateway.app) as client:
        assert client.post("/api/voice/tools/recommend", content="x").status_code == 415
        assert client.post("/api/voice/tools/recommend", content=b"x" * (voice_gateway.MAX_BODY + 1), headers={"content-type": "application/json"}).status_code == 413


def test_gateway_forwards_only_to_fixed_planner_and_preserves_auth(monkeypatch):
    received = []
    class Upstream:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def post(self, url, **kwargs):
            received.append((url, kwargs))
            return httpx.Response(401, json={"detail": "Invalid tool credentials"})
    monkeypatch.setattr(voice_gateway.httpx, "AsyncClient", lambda **_: Upstream())
    with TestClient(voice_gateway.app) as client:
        response = client.post("/api/voice/tools/recommend", json={"message": "test"}, headers={"X-Qala-Tool-Secret": "fixture", "Authorization": "unrelated"})
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert received[0][0] == "http://127.0.0.1:8000/api/voice/tools/recommend"
    assert received[0][1]["headers"] == {"Content-Type": "application/json", "X-Qala-Tool-Secret": "fixture"}


def test_gateway_sanitizes_upstream_network_errors(monkeypatch):
    class Upstream:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def post(self, *_args, **_kwargs): raise httpx.ConnectError("private network details")
    monkeypatch.setattr(voice_gateway.httpx, "AsyncClient", lambda **_: Upstream())
    with TestClient(voice_gateway.app) as client:
        response = client.post("/api/voice/tools/recommend", json={})
    assert response.status_code == 502
    assert response.json() == {"detail": "Planner temporarily unavailable"}
