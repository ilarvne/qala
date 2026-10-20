"""Provider-free default tests must never spend real configured credentials."""
import pytest
import os

PROVIDER_KEYS = ("OPENAI_API_KEY", "ELEVENLABS_API_KEY", "TWILIO_AUTH_TOKEN", "VOICE_TOOL_SECRET", "ALEMPLUS_API_KEY", "ALEMPLUS_EMBED_KEY", "ALEMPLUS_RERANK_KEY", "ALEMPLUS_STT_KEY", "ALEMPLUS_STT_KK_KEY", "GOOGLE_PLACES_API_KEY", "TWOGIS_API_KEY")


def pytest_sessionstart(session):
    # Runs before test-module imports and load_dotenv. Present-but-empty values
    # prevent a private developer .env from being reloaded into the test suite.
    for name in PROVIDER_KEYS:
        os.environ[name] = ""
    os.environ["QALA_LLM_PROVIDER"] = "local"
    os.environ["QALA_RERANK_PROVIDER"] = "none"
    os.environ["QALA_EMBEDDINGS"] = "hash"
    os.environ["QALA_WEATHER"] = "off"
    os.environ["QALA_EVENTS"] = "off"


@pytest.fixture(autouse=True)
def no_live_alemplus_credentials(monkeypatch):
    monkeypatch.setenv("QALA_WEATHER", "off")
    monkeypatch.setenv("QALA_EVENTS", "off")
    for name in PROVIDER_KEYS:
        monkeypatch.setenv(name, "")
    for name in ("QALA_LLM_PROVIDER", "QALA_RERANK_PROVIDER"):
        monkeypatch.delenv(name, raising=False)
