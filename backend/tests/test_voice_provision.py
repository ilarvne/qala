"""Real HTTP boundaries mocked; no provider success is claimed by these tests."""
import copy
import json
from pathlib import Path

import httpx
import pytest
from dotenv import dotenv_values

from backend.models import RecommendRequest
from scripts.provision_elevenlabs import (
    API, Provider, ProvisionError, agent_payload, check, landmarks, main,
    provision, public_origin, save_environment, tool_payload, merge_managed,
)

ORIGIN = "https://qala.example.com"
TOOL_SECRET = "webhook-secret-used-only-in-tests-1234567890"
API_KEY = "provider-key-used-only-in-tests"


class Workspace:
    """An in-memory provider behind httpx's actual transport interface."""
    def __init__(self):
        self.resources = {}
        self.calls = []
        self.fail_agent_create = False
        self.reject_secret_create = False

    def handle(self, request):
        assert request.url.host == "api.elevenlabs.io"
        assert request.headers["xi-api-key"] == API_KEY
        path, method = request.url.path, request.method
        body = json.loads(request.content) if request.content else None
        self.calls.append((method, path, body))
        if path == "/v1/voices/voice_test" and method == "GET":
            return httpx.Response(200, json={"voice_id": "voice_test"})
        if path == "/v1/convai/conversation/get-signed-url":
            return httpx.Response(200, json={"signed_url": "wss://api.elevenlabs.io/session?token=DO-NOT-PRINT"})
        if method == "GET" and path in self.resources:
            return httpx.Response(200, json=copy.deepcopy(self.resources[path]))
        if method == "POST":
            if path == "/v1/convai/secrets":
                if self.reject_secret_create:
                    return httpx.Response(422, json={"detail": "rejected"})
                data = {"type": "stored", "secret_id": "secret_test", "name": body["name"]}
                self.resources[path + "/secret_test"] = data
            elif path == "/v1/convai/tools":
                data = {"id": "tool_test", **body}
                self.resources[path + "/tool_test"] = data
            elif path == "/v1/convai/agents/create":
                data = {"agent_id": "agent_test", **body}
                self.resources["/v1/convai/agents/agent_test"] = data
                if self.fail_agent_create:
                    # Remote creation succeeded, but its reply was lost.
                    raise httpx.ReadTimeout("lost response", request=request)
            else:
                return httpx.Response(404, json={})
            return httpx.Response(200, json=data)
        if method == "PATCH" and path in self.resources:
            def apply(previous, update):
                result = copy.deepcopy(previous)
                for key, value in update.items():
                    if key in {"language_presets", "dynamic_variable_placeholders", "built_in_tools"} or not isinstance(value, dict) or not isinstance(result.get(key), dict):
                        result[key] = copy.deepcopy(value)
                    else:
                        result[key] = apply(result[key], value)
                return result
            self.resources[path] = apply(self.resources[path], body)
            return httpx.Response(200, json=self.resources[path])
        return httpx.Response(404, json={"detail": "missing"})

    def provider(self):
        return Provider(API_KEY, httpx.Client(transport=httpx.MockTransport(self.handle)))


def config(**updates):
    return {"PUBLIC_BASE_URL": ORIGIN, "ELEVENLABS_VOICE_ID": "voice_test", "VOICE_TOOL_SECRET": TOOL_SECRET, **updates}


@pytest.mark.parametrize("url", [
    "http://qala.example.com", "https://localhost", "https://127.0.0.1", "https://10.0.0.2",
    "https://example.internal", "https://user:password@qala.example.com", "https://qala.example.com/api",
    "https://qala.example.com?secret=value", "https://qala.example.com#secret", "https://qala.example.com:invalid",
])
def test_invalid_public_origins_stop_before_sending_secrets(url):
    with pytest.raises(ProvisionError):
        public_origin(url)
    assert public_origin(ORIGIN + "/") == ORIGIN


def test_default_offline_plan_cannot_contact_provider_or_include_credentials(tmp_path, monkeypatch, capsys):
    env, plan = tmp_path / ".env", tmp_path / "plan.json"
    env.write_text(f"ELEVENLABS_API_KEY={API_KEY}\nVOICE_TOOL_SECRET={TOOL_SECRET}\n")
    before = env.read_bytes()
    monkeypatch.setattr(httpx.Client, "request", lambda *a, **k: pytest.fail("offline plan made an HTTP request"))
    assert main(["--public-base-url", ORIGIN, "--env-file", str(env), "--plan-file", str(plan)]) == 0
    raw = plan.read_text() + capsys.readouterr().out
    assert API_KEY not in raw and TOOL_SECRET not in raw and "DO-NOT-PRINT" not in raw
    assert env.read_bytes() == before
    data = json.loads(plan.read_text())
    assert data["provider_requests_made"] is False and data["live_verified"] is False
    assert data["tool"]["tool_config"]["api_schema"]["request_headers"]["X-Qala-Tool-Secret"] == {"secret_id": "<workspace-secret-id-from-apply>"}
    prompt = data["agent"]["conversation_config"]["agent"]["prompt"]["prompt"]
    assert "{{context}}" in prompt and "{{language}}" in prompt
    assert "{{QALA_VERIFIED_LANDMARKS}}" not in prompt
    for place in landmarks():
        assert place["source"] in prompt


def test_tool_body_matches_backend_contract_without_persistent_memory_fields():
    tool = tool_payload(ORIGIN, "secret_test")["tool_config"]
    schema = tool["api_schema"]["request_body_schema"]
    assert "session_id" not in schema["properties"] and "remember" not in schema["properties"]
    assert {"location", "duration_minutes", "message"} <= set(schema["required"])
    assert "airport_transfer_minutes" in schema["properties"]
    sample = {"message": "Architecture", "location": {k: landmarks()[0][k] for k in ("lat", "lon")}, "duration_minutes": 60,
              "interests": ["architecture"], "language": "kk", "accessible": False, "indoor": False, "group_size": 2}
    parsed = RecommendRequest.model_validate(sample)
    assert parsed.remember is False and parsed.session_id is None
    assert tool["api_schema"]["request_headers"]["X-Qala-Tool-Secret"] == {"secret_id": "secret_test"}


def test_full_planner_result_event_is_in_provider_conversation_configuration():
    payload = agent_payload("voice_test", "tool_test")
    conversation = payload["conversation_config"]
    assert "client_events" not in conversation
    assert {"audio", "user_transcript", "agent_response", "agent_tool_response_full_payload"} <= set(conversation["conversation"]["client_events"])
    assert payload["platform_settings"]["auth"]["enable_auth"] is True


def test_apply_is_idempotent_and_persists_private_server_ids(tmp_path):
    workspace = Workspace()
    env, state = tmp_path / ".env", tmp_path / "private/receipt.json"
    env.write_text("# existing configuration\nUNRELATED='keep me'\n")
    result = provision(config(), env, state, workspace.provider())
    assert result["configuration_verified"] is True and result["conversation_live_verified"] is False
    assert result["agent_id"] == "agent_test"
    saved = dotenv_values(env)
    assert saved["VOICE_TOOL_SECRET"] == TOOL_SECRET and saved["UNRELATED"] == "keep me"
    assert saved["ELEVENLABS_AGENT_ID"] == "agent_test" and saved["ELEVENLABS_TOOL_ID"] == "tool_test"
    assert env.stat().st_mode & 0o777 == state.stat().st_mode & 0o777 == 0o600
    assert API_KEY not in env.read_text() and TOOL_SECRET not in state.read_text()
    created = [p for m, p, _ in workspace.calls if m == "POST"]
    assert created == ["/v1/convai/secrets", "/v1/convai/tools", "/v1/convai/agents/create"]
    workspace.calls.clear()
    provision(config(), env, state, workspace.provider())
    assert not [c for c in workspace.calls if c[0] in ("POST", "PATCH")]
    agent = workspace.resources["/v1/convai/agents/agent_test"]
    assert agent["platform_settings"]["auth"]["enable_auth"] is True
    assert agent["platform_settings"]["privacy"]["retention_days"] == 0
    assert agent["conversation_config"]["tts"]["model_id"] == "eleven_v4_turbo"
    assert set(agent["conversation_config"]["language_presets"]) == {"en", "ru", "kk", "de", "fr", "es", "zh", "ar", "tr", "hi", "ja", "ko", "uk", "it", "ky", "az"}
    detector = agent["conversation_config"]["agent"]["prompt"]["built_in_tools"]["language_detection"]
    assert detector["type"] == "system" and detector["params"]["system_tool_type"] == "language_detection"


def test_existing_agent_recovers_attached_qala_tool_without_duplicate_creation(tmp_path):
    workspace = Workspace()
    agent = agent_payload("voice_test", "tool_test")
    agent["conversation_config"]["agent"]["prompt"]["tool_ids"] = ["tool_other", "tool_test"]
    workspace.resources = {
        "/v1/convai/agents/agent_existing": {"agent_id": "agent_existing", **agent},
        "/v1/convai/tools/tool_other": {"id": "tool_other", "tool_config": {"type": "client", "name": "another_tool"}},
        "/v1/convai/tools/tool_test": {"id": "tool_test", **tool_payload(ORIGIN, "secret_test")},
        "/v1/convai/secrets/secret_test": {"secret_id": "secret_test", "name": "Qala tool secret"},
    }
    result = provision(config(ELEVENLABS_AGENT_ID="agent_existing"), tmp_path / ".env", tmp_path / "receipt.json", workspace.provider())
    assert result["agent_id"] == "agent_existing" and result["tool_id"] == "tool_test"
    assert not [c for c in workspace.calls if c[0] == "POST"]
    assert workspace.resources["/v1/convai/agents/agent_existing"]["conversation_config"]["agent"]["prompt"]["tool_ids"] == ["tool_other", "tool_test"]


def test_language_update_preserves_unmanaged_provider_settings_and_never_patches_readonly_metadata(tmp_path):
    workspace = Workspace()
    env, state = tmp_path / ".env", tmp_path / "receipt.json"
    provision(config(), env, state, workspace.provider())
    agent = workspace.resources["/v1/convai/agents/agent_test"]
    agent["created_at_unix_secs"] = 12345
    agent["conversation_config"]["turn"] = {"turn_timeout": 12, "turn_eagerness": "patient"}
    agent["conversation_config"]["agent"]["prompt"]["max_tokens"] = 410
    agent["platform_settings"]["widget"] = {"variant": "compact"}
    agent["conversation_config"]["language_presets"].pop("fr")
    workspace.calls.clear()
    provision(config(), env, state, workspace.provider())
    patches = [body for method, path, body in workspace.calls if method == "PATCH" and "/agents/" in path]
    assert len(patches) == 1
    patch = patches[0]
    assert "agent_id" not in patch and "created_at_unix_secs" not in patch
    assert "turn" not in patch["conversation_config"]
    assert "platform_settings" not in patch
    assert "fr" in patch["conversation_config"]["language_presets"]
    saved = workspace.resources["/v1/convai/agents/agent_test"]
    assert saved["conversation_config"]["turn"] == {"turn_timeout": 12, "turn_eagerness": "patient"}
    assert saved["conversation_config"]["agent"]["prompt"]["max_tokens"] == 410
    assert saved["platform_settings"]["widget"] == {"variant": "compact"}


def test_spoken_language_translation_never_expands_the_planner_language_contract():
    payload = agent_payload("voice_test", "tool_test")
    config = payload["conversation_config"]
    variables = config["agent"]["dynamic_variables"]["dynamic_variable_placeholders"]
    assert variables["language"] == variables["planner_language"] == "en"
    prompt = config["agent"]["prompt"]["prompt"]
    assert "{{planner_language}}" in prompt
    assert "Translate the caller's request into concise English" in prompt
    assert "Never add or infer venue facts while translating" in prompt
    language = tool_payload(ORIGIN, "secret_test")["tool_config"]["api_schema"]["request_body_schema"]["properties"]["language"]
    assert language["enum"] == ["en", "ru", "kk"]
    assert all(preset["overrides"]["agent"]["language"] == code and len(preset["overrides"]["agent"]["first_message"]) > 30 for code, preset in config["language_presets"].items())


def test_partial_language_updates_send_complete_provider_replacement_maps(tmp_path):
    workspace = Workspace()
    env, state = tmp_path / ".env", tmp_path / "receipt.json"
    provision(config(), env, state, workspace.provider())
    saved = workspace.resources["/v1/convai/agents/agent_test"]["conversation_config"]
    saved["language_presets"].pop("fr")
    variables = saved["agent"]["dynamic_variables"]["dynamic_variable_placeholders"]
    variables.pop("planner_language")
    variables["unrelated_user_value"] = "preserve"
    workspace.calls.clear()
    provision(config(), env, state, workspace.provider())
    patch = next(body for method, path, body in workspace.calls if method == "PATCH" and "/agents/" in path)["conversation_config"]
    assert len(patch["language_presets"]) == 16
    assert set(patch["agent"]["dynamic_variables"]["dynamic_variable_placeholders"]) == {"language", "context", "planner_language", "unrelated_user_value"}
    actual = workspace.resources["/v1/convai/agents/agent_test"]["conversation_config"]
    assert {"en", "ru", "kk", "fr"} <= set(actual["language_presets"])
    assert actual["agent"]["dynamic_variables"]["dynamic_variable_placeholders"]["unrelated_user_value"] == "preserve"


def test_lost_creation_response_leaves_recoverable_receipt_and_stops_duplicate_retry(tmp_path):
    workspace = Workspace()
    workspace.fail_agent_create = True
    env, state = tmp_path / ".env", tmp_path / "receipt.json"
    with pytest.raises(ProvisionError, match="inspect provider state"):
        provision(config(), env, state, workspace.provider())
    assert dotenv_values(env)["VOICE_TOOL_SECRET"] == TOOL_SECRET
    assert json.loads(state.read_text())["pending_creation"] == "agent"
    workspace.calls.clear()
    with pytest.raises(ProvisionError, match="ELEVENLABS_AGENT_ID"):
        provision(config(), env, state, workspace.provider())
    assert workspace.calls == []
    result = provision(config(ELEVENLABS_AGENT_ID="agent_test"), env, state, workspace.provider())
    assert result["configuration_verified"] is True
    assert not [c for c in workspace.calls if c[0] == "POST"]


def test_authoritative_create_rejection_can_retry_after_configuration_is_fixed(tmp_path):
    workspace = Workspace()
    workspace.reject_secret_create = True
    env, state = tmp_path / ".env", tmp_path / "receipt.json"
    with pytest.raises(ProvisionError, match="HTTP 422"):
        provision(config(), env, state, workspace.provider())
    assert "pending_creation" not in json.loads(state.read_text())
    assert not workspace.resources
    workspace.reject_secret_create = False
    result = provision(config(), env, state, workspace.provider())
    assert result["configuration_verified"] is True
    assert result["agent_id"] == "agent_test"


def test_provider_error_cannot_reflect_credentials_to_terminal(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", API_KEY)
    env = tmp_path / ".env"
    def fail(self, *args, **kwargs):
        return httpx.Response(401, json={"detail": API_KEY + TOOL_SECRET})
    monkeypatch.setattr(httpx.Client, "request", fail)
    assert main(["--apply", "--public-base-url", ORIGIN, "--voice-id", "voice_test", "--env-file", str(env), "--state-file", str(tmp_path / "receipt.json")]) == 1
    captured = capsys.readouterr()
    assert "HTTP 401" in captured.err
    assert API_KEY not in captured.err and TOOL_SECRET not in captured.err
    assert not env.exists()


def test_check_uses_actual_http_boundaries_without_starting_conversation(tmp_path):
    workspace = Workspace()
    provision(config(), tmp_path / ".env", tmp_path / "receipt.json", workspace.provider())
    workspace.calls.clear()
    planner_calls = []
    def planner(request):
        planner_calls.append(request)
        assert str(request.url) == ORIGIN + "/api/voice/tools/recommend"
        assert request.headers["X-Qala-Tool-Secret"] == TOOL_SECRET
        assert json.loads(request.content)["remember"] is False
        return httpx.Response(200, json={"trace": [{"node": "hybrid_retrieval"}], "recommendations": []})
    result = check(config(ELEVENLABS_AGENT_ID="agent_test"), workspace.provider(), httpx.Client(transport=httpx.MockTransport(planner)))
    assert result["signed_url_issued"] and result["authenticated_planner_verified"]
    assert result["conversation_live_verified"] is False and result["phone_call_live_verified"] is False
    assert result["provider_webhook_execution_verified"] is False
    assert "DO-NOT-PRINT" not in json.dumps(result)
    assert len(planner_calls) == 1
    assert all(method == "GET" for method, _, _ in workspace.calls)


def test_check_rejects_public_agent_without_issuing_signed_url(tmp_path):
    workspace = Workspace()
    workspace.resources["/v1/convai/agents/agent_test"] = {"platform_settings": {"auth": {"enable_auth": False}}}
    with pytest.raises(ProvisionError, match="not private"):
        check(config(ELEVENLABS_AGENT_ID="agent_test"), workspace.provider(), httpx.Client())
    assert len(workspace.calls) == 1


def test_check_rejects_stale_prompt_or_unsafe_provider_settings_before_session_url(tmp_path):
    workspace = Workspace()
    provision(config(), tmp_path / ".env", tmp_path / "receipt.json", workspace.provider())
    workspace.calls.clear()
    workspace.resources["/v1/convai/agents/agent_test"]["platform_settings"]["privacy"]["retention_days"] = -1
    with pytest.raises(ProvisionError, match="differs from the intended"):
        check(config(ELEVENLABS_AGENT_ID="agent_test"), workspace.provider(), httpx.Client())
    assert not [p for _, p, _ in workspace.calls if "signed-url" in p]


def test_explicit_account_model_alternative_changes_provider_payload(tmp_path):
    workspace = Workspace()
    provision(config(ELEVENLABS_AGENT_MODEL_ID="eleven_v3_conversational"), tmp_path / ".env", tmp_path / "receipt.json", workspace.provider())
    assert workspace.resources["/v1/convai/agents/agent_test"]["conversation_config"]["tts"]["model_id"] == "eleven_v3_conversational"
    assert dotenv_values(tmp_path / ".env")["ELEVENLABS_AGENT_MODEL_ID"] == "eleven_v3_conversational"


def test_secret_environment_write_preserves_quotes_and_rejects_symlink(tmp_path):
    env = tmp_path / ".env"
    save_environment(env, {"VOICE_TOOL_SECRET": "complex'quote\\value" * 4})
    assert dotenv_values(env)["VOICE_TOOL_SECRET"] == "complex'quote\\value" * 4
    link = tmp_path / "link.env"
    link.symlink_to(env)
    before = env.read_bytes()
    with pytest.raises(ProvisionError, match="symlink"):
        save_environment(link, {"VOICE_TOOL_SECRET": "changed"})
    assert env.read_bytes() == before
