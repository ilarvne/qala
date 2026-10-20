"""Conversation and retrieval regressions against real graph/corpus, no LLM."""
import json
import os

import pytest
from fastapi.testclient import TestClient

from backend.context import minutes_in_message, resolve_constraints
from backend.main import app
from backend.memory import PreferenceMemory
from backend.models import MemoryUpdateRequest, RecommendRequest
from backend.retrieval import HybridPOIRetriever, interest_mentions


@pytest.fixture(scope="module")
def chat_client(tmp_path_factory):
    previous = {key: os.environ.get(key) for key in ("OPENAI_API_KEY", "QALA_EMBEDDINGS", "QALA_MEMORY_PATH")}
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ["QALA_EMBEDDINGS"] = "hash"
    os.environ["QALA_MEMORY_PATH"] = str(tmp_path_factory.mktemp("conversation-memory") / "preferences.sqlite3")
    with TestClient(app) as client:
        yield client
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def body(message, **values):
    return {"message": message, "location": {"lat": 51.0897, "lon": 71.4073}, "duration_minutes": 75,
            "starts_at": "2026-10-20T14:00:00+05:00", **values}


def turn(client, message, previous=None, **values):
    result = client.post("/api/chat", json=body(message, **({"conversation": previous["conversation"]} if previous else {}), **values))
    assert result.status_code == 200, result.text
    return result.json()


def test_followup_keeps_category_and_applies_indoor_and_shorter_budget(chat_client):
    first = turn(chat_client, "Coffee nearby")
    second = turn(chat_client, "Only indoors, make it 40 minutes", first)
    assert first["recommendations"] and second["recommendations"]
    assert second["context"]["conversation_applied"] is True
    assert second["context"]["indoor"] is True
    assert all(p["category"] == "cafe" for p in second["recommendations"])
    assert second["context"]["requested_minutes"] == 40
    assert second["route"]["total_minutes"] <= 40


def test_alternatives_exclude_previous_real_ids_but_keep_coffee(chat_client):
    first = turn(chat_client, "Coffee nearby")
    alternative = turn(chat_client, "Show alternatives", first)
    assert alternative["recommendations"]
    assert {p["id"] for p in first["recommendations"]}.isdisjoint(p["id"] for p in alternative["recommendations"])
    assert all(p["category"] == "cafe" for p in alternative["recommendations"])
    assert first["recommendations"][0]["id"] in alternative["conversation"]["excluded_ids"]


def test_new_category_replaces_old_and_reset_discards_exclusions(chat_client):
    first = turn(chat_client, "Coffee nearby")
    next_plan = turn(chat_client, "A park instead", first, duration_minutes=120)
    assert "coffee" not in next_plan["conversation"]["interests"]
    assert all(p["category"] == "park" for p in next_plan["recommendations"])
    alternative = turn(chat_client, "Show alternatives", first)
    reset = turn(chat_client, "Start over. Coffee nearby", alternative)
    assert reset["conversation"]["excluded_ids"] == []
    assert reset["context"]["conversation_applied"] is False


def test_negative_categories_never_become_positive_intent(chat_client):
    result = turn(chat_client, "A culture walk, no museums", duration_minutes=120,
                  location={"lat": 51.1283, "lon": 71.4305})
    assert result["recommendations"]
    assert "museum" in result["conversation"]["excluded_categories"]
    assert all(p["category"] != "museum" for p in result["recommendations"])
    positive, negative = interest_mentions("Хочу кофе, без музеев")
    assert "coffee" in positive and "museum" in negative and "museum" not in positive


def test_group_constraint_survives_category_change_until_explicitly_cleared():
    request = RecommendRequest.model_validate(body("A pub instead", interests=["family"], conversation={"interests": ["family", "coffee"]}))
    resolved = resolve_constraints(request, None, set())
    assert "family" in resolved["interests"]
    adult_request = RecommendRequest.model_validate(body("Museum without kids", conversation={"interests": ["family"]}))
    adult = resolve_constraints(adult_request, None, set())
    assert "family" not in adult["interests"] and "museum" not in adult["excluded_categories"]


def test_max_walking_budget_is_cumulative_hard_constraint(chat_client):
    first = turn(chat_client, "A culture walk", duration_minutes=120, location={"lat": 51.1283, "lon": 71.4305})
    next_plan = turn(chat_client, "Keep walking under 10 minutes", first,
                     location={"lat": 51.1283, "lon": 71.4305})
    assert next_plan["conversation"]["max_walk_minutes"] == 10
    assert next_plan["route"]["walk_minutes"] <= 10
    assert next_plan["context"]["requested_minutes"] == 120


@pytest.mark.parametrize("message,language", [("A short architecture walk and coffee", "en"), ("Архитектурная прогулка и кофе", "ru"), ("Сәулет, серуен және кофе", "kk")])
def test_mixed_architecture_and_coffee_reserves_time_for_both_intents(chat_client, message, language):
    result = turn(chat_client, message, language=language, duration_minutes=60,
                  location={"lat": 51.1282, "lon": 71.4304})
    categories = {poi["category"] for poi in result["recommendations"]}
    assert "cafe" in categories and "culture" in categories
    assert result["route"]["total_minutes"] <= 60
    assert set(result["context"]["fulfilled_interests"]) == {"coffee", "culture"}
    assert result["context"]["unfulfilled_interests"] == []
    assert all(poi.get("poi_type") not in {"cinema", "library", "theatre"} for poi in result["recommendations"])


def test_short_mixed_intent_budget_reports_partial_coverage_without_overrun(chat_client):
    result = turn(chat_client, "Architecture walk and coffee", duration_minutes=30,
                  location={"lat": 51.1282, "lon": 71.4304})
    assert result["recommendations"] and result["route"]["total_minutes"] <= 30
    assert result["context"]["unfulfilled_interests"]
    fulfilled = {"coffee" if poi["category"] == "cafe" else "culture" for poi in result["recommendations"]}
    assert set(result["context"]["fulfilled_interests"]) == fulfilled
    assert set(result["context"]["unfulfilled_interests"]) == {"coffee", "culture"} - fulfilled


def test_airport_clarification_reply_preserves_departure_budget(chat_client):
    first = turn(chat_client, "I have 3 hours before my flight")
    assert first["clarifications"][0]["field"] == "airport_transfer_minutes"
    assert first["recommendations"] == []
    second = turn(chat_client, "20 minutes", first)
    assert second["context"]["requested_minutes"] == 180
    assert second["context"]["airport_transfer_minutes"] == 20
    assert second["context"]["available_minutes"] == 70
    assert second["route"]["total_minutes"] <= 70
    assert not second["clarifications"]


@pytest.mark.parametrize("message", ["На дорогу до аэропорта нужно 45 минут. До вылета всего 120 минут.",
    "До вылета всего 120 минут, на дорогу до аэропорта нужно 45 минут.",
    "The airport transfer takes about 45 minutes. I have 120 minutes before my flight."])
def test_natural_transfer_clause_does_not_replace_flight_deadline(chat_client, message):
    assert minutes_in_message(message) == 120
    result = turn(chat_client, message)
    assert result["context"]["requested_minutes"] == 120
    assert result["context"]["airport_transfer_minutes"] == 45
    assert result["context"]["available_minutes"] == 0
    assert result["recommendations"] == []
    assert not any(item["field"] == "airport_transfer_minutes" for item in result["clarifications"])


@pytest.mark.parametrize("message,minutes", [("30–60 minutes outside", 60), ("A 45-minute walk", 45),
    ("На 45 минут", 45), ("1,5 часа", 90), ("Half an hour", 30), ("within 10 minutes walking", None)])
def test_explicit_duration_parser_ignores_subbudgets(message, minutes):
    assert minutes_in_message(message) == minutes


def test_untrusted_conversation_cannot_supply_facts_and_unknown_ids_are_ignored(chat_client):
    invalid = chat_client.post("/api/chat", json=body("Coffee", conversation={"source": "made up", "interests": ["coffee"]}))
    assert invalid.status_code == 422
    result = turn(chat_client, "Coffee nearby", conversation={"interests": ["coffee"], "excluded_ids": ["invented-rooftop"]})
    assert result["conversation"]["excluded_ids"] == []
    assert all(p["id"].startswith("osm-") and p["rating"] is None for p in result["recommendations"])


def test_preference_edit_requires_consent_and_applies_without_chat_storage(chat_client):
    sid = "conversation-memory-capability-8abe62631"
    assert chat_client.post(f"/api/memory/{sid}", json={"interests": ["coffee"]}).status_code == 422
    result = chat_client.post(f"/api/memory/{sid}", json={"consent": True, "interests": ["coffee", "raw private message"], "indoor": True, "duration_minutes": 45})
    assert result.status_code == 200
    prefs = result.json()["preferences"]
    assert prefs["interests"] == ["coffee"] and "location" not in prefs and "coarse_location" not in prefs
    next_plan = turn(chat_client, "Something nearby", session_id=sid)
    assert next_plan["recommendations"] and all(p["category"] == "cafe" for p in next_plan["recommendations"])
    assert next_plan["context"]["indoor"] is True
    assert "raw private" not in json.dumps(next_plan)
    chat_client.delete(f"/api/memory/{sid}")
    assert chat_client.get(f"/api/memory/{sid}").json()["preferences"] is None


def test_stale_client_consent_after_delete_cannot_recreate_memory(chat_client):
    sid = "stale-client-generation-session-292817"
    initial = chat_client.get(f"/api/memory/{sid}").json()
    assert initial["generation"] == 0
    first = turn(chat_client, "Coffee", session_id=sid, remember=True, memory_generation=0)
    assert first["context"]["preferences_remembered"] is True
    deleted = chat_client.delete(f"/api/memory/{sid}").json()
    assert deleted["generation"] == 1
    stale = turn(chat_client, "Coffee", session_id=sid, remember=True, memory_generation=0)
    assert stale["context"]["memory_revoked_during_request"] is True
    assert stale["context"]["memory_generation"] == 1
    assert chat_client.get(f"/api/memory/{sid}").json()["preferences"] is None
    fresh = turn(chat_client, "Coffee", session_id=sid, remember=True, memory_generation=1)
    assert fresh["context"]["preferences_remembered"] is True
    assert chat_client.get(f"/api/memory/{sid}").json()["generation"] == 1
    chat_client.delete(f"/api/memory/{sid}")


def test_stale_explicit_memory_post_cannot_recreate_deleted_preferences(chat_client):
    sid = "queued-memory-post-session-1029384"
    deleted = chat_client.delete(f"/api/memory/{sid}").json()
    rejected = chat_client.post(f"/api/memory/{sid}", json={"consent": True, "memory_generation": 0, "interests": ["coffee"]})
    assert rejected.status_code == 409
    assert chat_client.get(f"/api/memory/{sid}").json()["preferences"] is None
    fresh = chat_client.post(f"/api/memory/{sid}", json={"consent": True, "memory_generation": deleted["generation"], "interests": ["coffee"]}).json()
    assert fresh["preferences"]["interests"] == ["coffee"] and fresh["generation"] == deleted["generation"] + 1
    assert "memory_generation" not in fresh["preferences"]
    chat_client.delete(f"/api/memory/{sid}")


def test_revoked_local_read_preference_is_not_applied_even_if_server_record_remains(chat_client):
    sid = "locally-revoked-read-session-182716"
    chat_client.post(f"/api/memory/{sid}", json={"consent": True, "interests": ["coffee"], "indoor": True})
    result = turn(chat_client, "Something nearby", session_id=sid, remember=False, use_saved_preferences=False)
    assert result["context"]["preferences_applied"] is False
    assert result["context"]["indoor"] is False and "coffee" not in result["context"]["interests"]
    chat_client.delete(f"/api/memory/{sid}")


def test_explicit_message_booleans_override_ui_and_ui_overrides_prior():
    outdoor = RecommendRequest.model_validate(body("Outdoors please", indoor=True, conversation={"indoor": True}))
    assert resolve_constraints(outdoor, None, set())["indoor"] is False
    current_ui = RecommendRequest.model_validate(body("Show alternatives", indoor=False, accessible=False, conversation={"indoor": True, "accessible": True}))
    resolved = resolve_constraints(current_ui, None, set())
    assert resolved["indoor"] is False and resolved["accessible"] is False


def test_architecture_walk_avoids_cinemas_and_libraries(chat_client):
    result = turn(chat_client, "An architecture walk", duration_minutes=90,
                  location={"lat": 51.1283, "lon": 71.4305})
    assert result["recommendations"]
    assert all(p["poi_type"] not in {"cinema", "library", "theatre", "arts_centre", "community_centre"} for p in result["recommendations"])
    assert "little Astana escape" not in result["message"] and "90-minute limit" in result["message"]


def test_library_has_reading_action_and_realistic_visit_duration(chat_client):
    result = turn(chat_client, "A library for reading", duration_minutes=75,
                  location={"lat": 51.1283, "lon": 71.4305})
    assert result["recommendations"]
    assert all(p["poi_type"] == "library" and p["visit_minutes"] == 30 for p in result["recommendations"])
    assert "read" in result["recommendations"][0]["action"]
    assert "landmark" not in result["recommendations"][0]["why"]


def test_cinema_cannot_become_twelve_minute_landmark_stop(chat_client):
    result = turn(chat_client, "A cinema movie", duration_minutes=60,
                  location={"lat": 51.1283, "lon": 71.4305})
    assert not result["recommendations"]
    assert result["clarifications"][0]["field"] == "duration_minutes"


def test_named_stream_events_come_from_real_nodes_and_result_matches_source(chat_client):
    response = chat_client.post("/api/chat/stream", json=body("Coffee nearby"))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers.get("content-encoding") is None
    frames = [frame for frame in response.text.split("\n\n") if frame.strip()]
    events = [(frame.splitlines()[0].removeprefix("event: "), json.loads(frame.splitlines()[1].removeprefix("data: "))) for frame in frames]
    assert [payload["stage"] for event, payload in events if event == "status"] == ["retrieve", "rank", "validate", "compose"]
    assert events[-1][0] == "result"
    result = events[-1][1]
    assert result["recommendations"]
    assert any(step["node"] == "validate_plan" for step in result["trace"])
    assert result["retrieval"]["eligible_count"] < result["retrieval"]["corpus_count"]


def test_stream_failure_sanitizes_details_and_does_not_emit_fake_result(chat_client, monkeypatch):
    async def broken_stream(request):
        yield "status", {"stage": "retrieve"}
        raise RuntimeError("private-provider-key and exact user coordinate")
    monkeypatch.setattr(app.state.agent, "stream", broken_stream)
    response = chat_client.post("/api/chat/stream", json=body("Coffee"))
    assert "event: error" in response.text and "event: result" not in response.text
    assert "private-provider-key" not in response.text and "coordinate" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_inventory_pagination_and_details_preserve_source_and_photos(chat_client):
    response = chat_client.get("/api/pois", params={"category": "museum", "q": "National", "limit": 2}).json()
    assert len(response["pois"]) == 1
    poi = response["pois"][0]
    detail = chat_client.get(f"/api/pois/{poi['id']}").json()["poi"]
    assert detail == poi and "raw_tags" not in detail
    assert detail["source"]["url"].startswith("https://www.openstreetmap.org/")
    assert chat_client.get("/api/pois/invented").status_code == 404


def test_real_rating_and_rating_only_review_are_not_invented_or_discarded(chat_client):
    poi = chat_client.get("/api/pois/osm-node-14201388401").json()["poi"]
    result = turn(chat_client, "Overhead pub", location={"lat": poi["lat"], "lon": poi["lon"]}, starts_at="2026-10-20T20:00:00+05:00")
    selected = next(p for p in result["recommendations"] if p["id"] == poi["id"])
    assert selected["rating"] == poi["rating"] == 3.5 and selected["rating_count"] == 1
    assert selected["rating_source"] == poi["rating_source"]
    assert selected["reviews"] == poi["reviews"] and selected["reviews"][0]["text"] is None
    assert selected["reviews"][0]["signature_verified"] is True
    assert selected["photos"] == poi["photos"]


def test_private_venue_never_recommended_even_for_exact_name():
    source = {"name": "OpenStreetMap", "url": "https://www.openstreetmap.org/node/1"}
    pois = [{"id": "private", "name": "Secret Cafe", "names": {}, "description": "Coffee", "lat": 51.1, "lon": 71.4,
             "category": "cafe", "tags": ["coffee"], "source": source, "indoor": True, "wheelchair": "yes", "recommendable": False}]
    retriever = HybridPOIRetriever(pois)
    assert retriever.search("Secret Cafe", (51.1, 71.4), ["coffee"], False, False, 1000) == []


def test_family_context_excludes_adult_nightlife_even_if_query_mentions_it():
    poi = {"id": "nightclub", "name": "Night venue", "description": "Nightlife", "lat": 51.1, "lon": 71.4,
           "category": "nightlife", "tags": ["nightlife"], "source": {"url": "https://www.openstreetmap.org/node/1"}, "indoor": True, "wheelchair": "yes"}
    retriever = HybridPOIRetriever([poi])
    assert retriever.search("Nightlife with children", (51.1, 71.4), ["family", "nightlife"], False, False, 1000) == []


def test_new_preference_edit_cannot_be_overwritten_by_older_inflight_plan(tmp_path):
    memory = PreferenceMemory(tmp_path / "preferences.sqlite3")
    request = RecommendRequest.model_validate(body("Coffee", session_id="memory-edit-session-12345678", remember=True))
    _, generation = memory.snapshot(request.session_id)
    memory.update(request.session_id, MemoryUpdateRequest(consent=True, interests=["museum"], indoor=True))
    assert memory.save(request, ["coffee"], expected_generation=generation) is None
    assert memory.get(request.session_id)["interests"] == ["museum"]


def test_geographic_filter_precedes_vector_topk():
    source = {"name": "OSM", "url": "https://www.openstreetmap.org/node/1"}
    pois = [{"id": "near", "name": "Nearby cafe", "description": "Coffee", "category": "cafe", "tags": ["coffee"],
             "source": source, "lat": 51.1, "lon": 71.4, "indoor": True, "wheelchair": "unknown"},
            {"id": "far", "name": "Exact coffee match", "description": "Coffee", "category": "cafe", "tags": ["coffee"],
             "source": source, "lat": 43.2, "lon": 76.8, "indoor": True, "wheelchair": "unknown"}]
    retriever = HybridPOIRetriever(pois)
    found, report = retriever.search_with_report("coffee", (51.1, 71.4), ["coffee"], False, False, 1000)
    assert [p["id"] for p in found] == ["near"]
    assert report["vector_candidates"] == 1 and report["excluded_counts"]["distance"] == 1
    assert found[0]["retrieval_evidence"]["matched_interests"] == ["coffee"]
