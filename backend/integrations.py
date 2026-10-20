"""Honest capability status: configured is distinct from a successful call."""
from __future__ import annotations

from datetime import datetime, timezone
import os

from .alemplus import integration_status, provider_observation
from .models import IntegrationCapability, IntegrationsResponse


def describe_integrations(agent, *, twogis=None) -> IntegrationsResponse:
    items: list[IntegrationCapability] = []

    def add(identifier, name, configured, source, detail, capabilities, observation=None, status=None):
        observed = observation or {}
        verified = observed.get("live_verified", False)
        state = status or ("key_required" if not configured else "active" if verified else "unavailable" if observed.get("checked_at") else "configured")
        items.append(IntegrationCapability(id=identifier, name=name, configured=bool(configured), status=state,
                                          live_verified=bool(verified), last_checked_at=observed.get("checked_at"),
                                          source_url=source, detail=detail, capabilities=capabilities))

    add("osm", "OpenStreetMap", True, "https://www.openstreetmap.org/copyright",
        "Automated local POI inventory with per-record provenance; source coverage and freshness vary.", ["local_poi_search", "source_provenance"], status="active")
    overture = next((item for item in agent.dataset.get("metadata", {}).get("additional_collections", [])
                     if isinstance(item, dict) and item.get("provider") == "Overture Maps" and item.get("release")), None)
    if overture:
        # Release comes from the published inventory manifest, never a claim
        # that a live upstream API is connected to the browser.
        release = str(overture["release"])[:40]
        add("overture", "Overture Maps", True, "https://docs.overturemaps.org/attribution/",
            f"Imported Places release {release}, reconciled with local source identities. Release confidence is an existence signal, not a customer rating or proof of current access.",
            ["imported_poi_inventory", "release_provenance"], status="active")
    add("openfreemap", "OpenFreeMap / MapLibre", True, "https://openfreemap.org/quick_start/",
        "Embedded schematic footprint extrusions; not verified landmark geometry or photogrammetry.", ["embedded_map", "schematic_3d", "flat_2d"], status="available")
    add("wikimedia", "Wikimedia Commons / Wikidata", True, "https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia",
        "Licensed images from matched source identities; missing photos are not generated or replaced with another venue.", ["licensed_poi_photos", "photo_attribution"], status="active")
    add("operator_metadata", "Venue websites", True, "https://www.robotstxt.org/robotstxt.html",
        "Bounded robots-aware collection of public operator metadata. Unlicensed image links and self-published ratings are not independent reviews.", ["operator_metadata", "robots_aware_crawling"], status="active" if agent.dataset.get("metadata", {}).get("operator_sources") else "available")
    add("mangrove", "Mangrove Reviews", True, "https://mangrove.reviews/standard",
        "Only matching public reviews and ratings with source provenance are used; a signed review is not proof of a verified customer.", ["public_ratings", "public_reviews"], status="active" if any(p.get("rating_source") for p in agent.dataset["pois"]) else "available")
    weather = agent.weather.status()
    add("weather", "Open-Meteo", weather["enabled"], "https://open-meteo.com/en/terms",
        "City forecast only; no precise user location is sent. CC BY 4.0 attribution. The free API is for noncommercial use; commercial deployment requires its plan.",
        ["hourly_city_forecast", "weather_adaptation"], weather, "disabled" if not weather["enabled"] else None)
    events = agent.events.status()
    add("events", "Astana Venue Management", events["enabled"], "https://a-vm.kz/events/",
        "Robots-permitted official calendar metadata. Dates may lack start time, venue or ticket availability; this is not the city's complete event calendar.",
        ["official_dated_events"], events, "disabled" if not events["enabled"] else None)
    for identifier, value in integration_status().items():
        labels = {"llm": "Grounded language generation", "alemplus_rerank": "AlemPlus reranker", "alemplus_embeddings": "AlemPlus embeddings", "alemplus_stt": "AlemPlus dictation", "alemplus_stt_kk": "AlemPlus Kazakh dictation"}
        detail = "The current process reports configuration separately from a completed provider call."
        if identifier == "alemplus_embeddings":
            detail = "The cloud embedding adapter is configured for explicit probes; the active document index is local, not a cloud-built index."
        add(identifier, labels[identifier], value["configured"], "https://doc.alem.ai/" if value.get("provider") == "AlemPlus" else "https://platform.openai.com/docs/overview",
            detail, [identifier], value)
    add("walking_router", "Valhalla", True, "https://valhalla.github.io/valhalla/api/turn-by-turn/api-reference/",
        "Street-graph pedestrian routing refines the plan preview before directions start. Route coordinates are sent transiently; surface accessibility is not verified.",
        ["pedestrian_directions", "route_geometry"], provider_observation("walking_router"))
    add("elevenlabs_tts", "ElevenLabs speech", bool(os.getenv("ELEVENLABS_API_KEY") and os.getenv("ELEVENLABS_VOICE_ID")), "https://elevenlabs.io/docs/api-reference/text-to-speech/convert",
        "Speech synthesis is verified only after a successful response in this process.", ["speech_synthesis"], provider_observation("elevenlabs_tts"))
    add("elevenlabs_agent", "ElevenLabs conversation", bool(os.getenv("ELEVENLABS_API_KEY") and os.getenv("ELEVENLABS_AGENT_ID")), "https://elevenlabs.io/docs/agents-platform/api-reference/conversations/get-signed-url",
        "A successful private-session API call verifies session issuance, not a physical microphone test or a phone call.", ["private_voice_session"], provider_observation("elevenlabs_session"))
    add("twilio", "Twilio", all(os.getenv(key) for key in ("TWILIO_AUTH_TOKEN", "ELEVENLABS_API_KEY", "ELEVENLABS_AGENT_ID", "PUBLIC_BASE_URL")), "https://www.twilio.com/docs/voice",
        "Authenticated incoming-call adapter exists; an operator-provisioned number and telephony account are required. No live phone call is claimed.", ["incoming_voice_webhook"])
    add("google_places", "Google Places", False, "https://developers.google.com/maps/documentation/places/web-service/policies",
        "Google Places photos and results displayed on a map require a Google map under its policies. They are not an interchangeable photo source for this MapLibre map.", [], status="restricted")
    twogis_status = twogis.status() if twogis is not None else {"configured": bool(os.getenv("TWOGIS_API_KEY")), "live_verified": False, "checked_at": None}
    add("twogis", "2GIS", twogis_status["configured"], "https://docs.2gis.com/en/api/search/places/overview",
        "On-demand provider profiles use the owned server key. Ratings remain provider-specific; galleries are links, not downloaded photographs. No completed-response cache or POI/RAG import is enabled by default. Display and reuse remain subject to the account's applicable terms.",
        ["place_source_details", "rating_statistics", "opening_hours", "provider_gallery_links"], twogis_status)
    add("foursquare", "Foursquare Places", False, "https://docs.foursquare.com/developer/reference/places-api-overview",
        "No runtime provider adapter or authenticated account is configured; this build does not claim Foursquare review or photo coverage.", [], status="not_integrated")
    return IntegrationsResponse(checked_at=datetime.now(timezone.utc).isoformat(), integrations=items)
