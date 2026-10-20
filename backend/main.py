from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from twilio.request_validator import RequestValidator

from .agent import CityAgent
from .alemplus import ProviderUnavailable, chat_configuration, integration_status, transcribe_audio, record_status
from .integrations import describe_integrations
from .memory import PreferenceMemory, StaleConsentGeneration
from .models import MemoryUpdateRequest, RecommendRequest, SpeechRequest, VoiceSessionRequest, IntegrationsResponse, EventsContext
from datetime import datetime
from .navigation import NavigationRequest, WalkingRouter
from .twogis import TwoGIS

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
DATASET_PATH = ROOT / "data/pois.json"


@asynccontextmanager
async def lifespan(app: FastAPI):
    dataset = json.loads(DATASET_PATH.read_text())
    memory = PreferenceMemory(Path(os.getenv("QALA_MEMORY_PATH", ROOT / ".local/preferences.sqlite3")))
    app.state.dataset = dataset
    app.state.memory = memory
    app.state.agent = CityAgent(dataset, memory)
    app.state.started = time.monotonic()
    app.state.walking_router = WalkingRouter()
    app.state.twogis = TwoGIS()
    try:
        yield
    finally:
        await app.state.twogis.close()


app = FastAPI(title="Qala · Astana city companion", version="1.0.0", lifespan=lifespan,
              description="Source-grounded POI retrieval, LangGraph planning, opt-in coarse memory and optional ElevenLabs voice.")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000").split(","), allow_methods=["GET", "POST", "DELETE"], allow_headers=["Content-Type", "X-Qala-Tool-Secret"])
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)

# Per-process bounded limiter: enough for a hackathon demo, not a distributed
# abuse-control system. Keys are transient salted IP hashes; no persisted IPs.
_rate: dict[str, deque] = defaultdict(deque)
_rate_salt = os.urandom(16)


def rate_limit(request: Request, bucket: str, limit: int):
    client = request.client.host if request.client else "local"
    key = hashlib.sha256(_rate_salt + (bucket + client).encode()).hexdigest()
    now = time.monotonic()
    queue = _rate[key]
    while queue and queue[0] < now - 60:
        queue.popleft()
    if len(queue) >= limit:
        raise HTTPException(429, "Please wait a moment before trying again", headers={"Retry-After": "60"})
    queue.append(now)
    if len(_rate) > 10000:
        for old in list(_rate):
            if not _rate[old] or _rate[old][-1] < now - 60:
                del _rate[old]


def eleven_config(agent: bool = False):
    key = os.getenv("ELEVENLABS_API_KEY")
    identifier = os.getenv("ELEVENLABS_AGENT_ID" if agent else "ELEVENLABS_VOICE_ID")
    if not key or not identifier:
        raise HTTPException(503, "ElevenLabs voice is not configured. Add server-side ELEVENLABS_API_KEY and " + ("ELEVENLABS_AGENT_ID" if agent else "ELEVENLABS_VOICE_ID") + ". Text recommendations remain available.")
    return key, identifier


@app.get("/api/health")
async def health(request: Request):
    data = request.app.state.dataset
    return {"status": "ok", "service": "qala", "mode": "llm-assisted" if chat_configuration() else "grounded-demo",
            "graph": "LangGraph StateGraph", "retrieval": "BM25 + LangChain vectors + interest and geo ranking", "embedding_mode": request.app.state.agent.retriever.embedding_mode,
            "dataset": {**data["metadata"], "query": None}, "poi_count": len(data["pois"]),
            "integrations": {**integration_status(),
                             "elevenlabs_tts": {"configured": bool(os.getenv("ELEVENLABS_API_KEY") and os.getenv("ELEVENLABS_VOICE_ID")), "live_verified": False},
                             "elevenlabs_agent": {"configured": bool(os.getenv("ELEVENLABS_API_KEY") and os.getenv("ELEVENLABS_AGENT_ID")), "live_verified": False},
                             "twilio": {"configured": all(os.getenv(k) for k in ("TWILIO_AUTH_TOKEN", "ELEVENLABS_API_KEY", "ELEVENLABS_AGENT_ID", "PUBLIC_BASE_URL")), "live_verified": False},
                             "walking_router": {"configured": True, "provider": "Valhalla", "mode": "pedestrian street routing", "live_verified": False}},
            "privacy": "No exact location or messages persisted; consent-only preferences expire after 30 days", "uptime_seconds": round(time.monotonic() - request.app.state.started, 1)}


@app.get("/api/integrations", response_model=IntegrationsResponse)
async def integrations(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return describe_integrations(request.app.state.agent, twogis=request.app.state.twogis)


@app.get("/api/events", response_model=EventsContext)
async def city_events(request: Request, response: Response, starts_at: datetime | None = None,
                      days: int = Query(default=14, ge=1, le=30)):
    from .agent import ALMATY
    rate_limit(request, "events", 30)
    response.headers["Cache-Control"] = "no-store"
    return await request.app.state.agent.events.upcoming(starts_at or datetime.now(ALMATY), days=days)


@app.get("/api/pois")
async def pois(request: Request, category: str | None = None, q: str = Query(default="", max_length=150),
               limit: int | None = Query(default=None, ge=1, le=1000), offset: int = Query(default=0, ge=0),
               include_closed: bool = False):
    data = request.app.state.dataset
    # Return normalized source-backed fields; raw tags are in the downloadable
    # dataset but not necessary for UI display.
    # Keep closed history auditable without suggesting it as a current place.
    # Nonrecommendable utilities still belong in ordinary place search.
    selected = [p for p in data["pois"] if (include_closed or str(p.get("operating_status", "")).strip().casefold() != "closed")
                and (not category or p["category"] == category)]
    if q.strip():
        tokens = q.casefold().split()
        selected = [p for p in selected if all(token in " ".join([p["name"], *p.get("names", {}).values(), p.get("description", ""), p["category"], *p.get("tags", [])]).casefold() for token in tokens)]
    total = len(selected)
    selected = selected[offset:offset + limit if limit is not None else None]
    return {"pois": [{k: v for k, v in p.items() if k != "raw_tags"} for p in selected], "metadata": data["metadata"], "total": total, "offset": offset, "limit": limit}


@app.get("/api/pois/map")
async def poi_map(request: Request, response: Response):
    """The complete public inventory, without descriptions or raw source tags.

    Closed history remains available through /api/pois?include_closed=true.
    Only open-licensed corpus fields enter this source; provider profiles never do.
    """
    response.headers["Cache-Control"] = "public, max-age=60"
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": poi["id"], "geometry": {"type": "Point", "coordinates": [poi["lon"], poi["lat"]]},
         "properties": {"id": poi["id"], "name": poi["name"], "category": poi["category"],
                        **{f"name_{lang}": name for lang, name in poi.get("names", {}).items() if lang in {"ru", "en", "kk"} and name}}}
        for poi in request.app.state.dataset["pois"]
        if str(poi.get("operating_status", "")).strip().casefold() != "closed"
    ]}


@app.get("/api/pois/{poi_id}")
async def poi_detail(poi_id: str, request: Request):
    poi = request.app.state.agent.retriever.by_id.get(poi_id)
    if poi is None:
        raise HTTPException(404, "Place not found in the source dataset")
    return {"poi": {key: value for key, value in poi.items() if key != "raw_tags"}}


@app.get("/api/pois/{poi_id}/sources/2gis")
async def twogis_source(poi_id: str, request: Request, response: Response,
                        language: str = Query(default="ru", pattern="^(ru|en|kk)$")):
    # One explicit plan can display three source profiles. Allow ten such
    # interactions per minute while the provider client retains its own budget.
    rate_limit(request, "twogis-source", 30)
    response.headers["Cache-Control"] = "no-store"
    poi = request.app.state.agent.retriever.by_id.get(poi_id)
    if poi is None:
        raise HTTPException(404, "Place not found in the source dataset")
    return await request.app.state.twogis.lookup(poi, language=language)


@app.post("/api/recommend")
async def recommend(body: RecommendRequest, request: Request):
    rate_limit(request, "recommend", 60)
    start = time.perf_counter()
    result = await request.app.state.agent.recommend(body)
    result["elapsed_ms"] = round((time.perf_counter() - start) * 1000)
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@app.post("/api/chat")
async def chat(body: RecommendRequest, request: Request):
    """Conversational planning with the same grounded contract as recommend."""
    return await recommend(body, request)


@app.post("/api/chat/stream")
async def chat_stream(body: RecommendRequest, request: Request):
    rate_limit(request, "recommend", 60)
    async def events():
        start = time.perf_counter()
        try:
            async for event, payload in request.app.state.agent.stream(body):
                if await request.is_disconnected():
                    return
                if event == "result":
                    payload["elapsed_ms"] = round((time.perf_counter() - start) * 1000)
                yield f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
        except Exception:
            yield 'event: error\ndata: {"message":"The assistant could not finish this request. Please try again."}\n\n'
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.post("/api/navigation/route")
async def navigation_route(body: NavigationRequest, request: Request):
    rate_limit(request, "navigation", 12)
    try:
        result = await request.app.state.walking_router.route(body)
    except HTTPException:
        record_status("walking_router", False)
        raise
    record_status("walking_router", True, status=200)
    return Response(json.dumps(result), media_type="application/json", headers={"Cache-Control": "no-store"})


@app.get("/api/memory/{session_id}")
async def get_memory(session_id: str, request: Request):
    if not 16 <= len(session_id) <= 128:
        raise HTTPException(422, "Invalid session capability")
    preferences, generation = request.app.state.memory.snapshot(session_id)
    return JSONResponse({"preferences": preferences, "generation": generation, "retention_days": 30, "precise_location_stored": False}, headers={"Cache-Control": "no-store"})


@app.delete("/api/memory/{session_id}")
async def delete_memory(session_id: str, request: Request):
    if not 16 <= len(session_id) <= 128:
        raise HTTPException(422, "Invalid session capability")
    generation = request.app.state.memory.delete(session_id)
    return JSONResponse({"deleted": True, "preferences": None, "generation": generation}, headers={"Cache-Control": "no-store"})


@app.post("/api/memory/{session_id}")
async def edit_memory(session_id: str, body: MemoryUpdateRequest, request: Request):
    if not 16 <= len(session_id) <= 128:
        raise HTTPException(422, "Invalid session capability")
    rate_limit(request, "memory", 30)
    try:
        request.app.state.memory.update(session_id, body)
    except StaleConsentGeneration:
        raise HTTPException(409, "Saved preferences changed. Refresh them before saving.", headers={"Cache-Control": "no-store"})
    preferences, generation = request.app.state.memory.snapshot(session_id)
    return JSONResponse({"preferences": preferences, "generation": generation, "retention_days": 30, "precise_location_stored": False}, headers={"Cache-Control": "no-store"})


@app.post("/api/voice/speech")
async def speech(body: SpeechRequest, request: Request):
    rate_limit(request, "speech", 10)
    key, voice = eleven_config()
    # Eleven v3 supports Kazakh; multilingual_v2 does not. Model may be changed
    # explicitly by a deployer who has verified their language/voice support.
    model = os.getenv("ELEVENLABS_MODEL_ID", "eleven_v3")
    try:
        async with httpx.AsyncClient(timeout=35) as client:
            response = await client.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice}", params={"output_format": "mp3_44100_128"},
                headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
                json={"text": body.text, "model_id": model, "language_code": body.language})
        if response.status_code != 200:
            record_status("elevenlabs_tts", False, status=response.status_code)
            raise HTTPException(502, "ElevenLabs could not generate speech. Check voice/model/language access and credits in the provider dashboard.")
        record_status("elevenlabs_tts", True, status=200)
        return Response(response.content, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})
    except httpx.HTTPError:
        record_status("elevenlabs_tts", False)
        raise HTTPException(502, "Voice provider unavailable; use the text response")


@app.post("/api/voice/transcribe")
async def transcribe(request: Request, file: UploadFile = File(...), language: str = Form(default="en")):
    rate_limit(request, "transcribe", 10)
    if language not in {"en", "ru", "kk"}:
        raise HTTPException(422, "Choose English, Russian or Kazakh for dictation")
    mime = (file.content_type or "").split(";", 1)[0].strip().casefold()
    extensions = {"audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/wav": "wav", "audio/x-wav": "wav", "audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/flac": "flac"}
    try:
        if mime not in extensions:
            raise HTTPException(415, "Use a supported audio recording")
        audio = await file.read(8 * 1024 * 1024 + 1)
        if len(audio) > 8 * 1024 * 1024:
            raise HTTPException(413, "The recording is too large. Record a shorter message.")
        if not audio:
            raise HTTPException(422, "No audio was received")
        result = await transcribe_audio(audio, "dictation." + extensions[mime], mime, language)
        if not result["text"]:
            raise HTTPException(422, "No speech was recognized. Try another recording.")
        return JSONResponse(result, headers={"Cache-Control": "no-store"})
    except ProviderUnavailable as error:
        raise HTTPException(503, str(error)) from None
    finally:
        await file.close()


@app.post("/api/voice/session")
async def voice_session(body: VoiceSessionRequest, request: Request):
    rate_limit(request, "voice-session", 10)
    key, agent = eleven_config(agent=True)
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get("https://api.elevenlabs.io/v1/convai/conversation/get-signed-url", params={"agent_id": agent}, headers={"xi-api-key": key})
        if response.status_code != 200:
            record_status("elevenlabs_session", False, status=response.status_code)
            raise HTTPException(502, "Unable to start ElevenLabs agent; check agent authentication and provider access")
        signed_url = response.json()["signed_url"]
        record_status("elevenlabs_session", True, status=200)
        return Response(json.dumps({"signed_url": signed_url, "provider": "elevenlabs", "language": body.language}), media_type="application/json", headers={"Cache-Control": "no-store"})
    except (httpx.HTTPError, KeyError, ValueError):
        record_status("elevenlabs_session", False)
        raise HTTPException(502, "Conversational voice provider unavailable")


@app.post("/api/voice/tools/recommend")
async def voice_tool(body: RecommendRequest, request: Request, x_qala_tool_secret: str | None = Header(default=None)):
    """Authenticated ElevenLabs server tool. The voice agent must ask location."""
    configured = os.getenv("VOICE_TOOL_SECRET")
    if not configured:
        raise HTTPException(503, "Voice server tool is not configured")
    if not hmac.compare_digest(x_qala_tool_secret or "", configured):
        raise HTTPException(401, "Invalid tool credentials")
    if "location" not in body.model_fields_set:
        raise HTTPException(422, "Ask the caller for a landmark or location before requesting recommendations")
    # A telephone call is never implicit consent to persistent memory.
    body = body.model_copy(update={"remember": False, "session_id": None})
    rate_limit(request, "voice-tool", 60)
    return await request.app.state.agent.recommend(body)


@app.post("/api/voice/twilio/incoming")
async def twilio_incoming(request: Request):
    token, public_base = os.getenv("TWILIO_AUTH_TOKEN"), os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    if not token or not public_base:
        raise HTTPException(503, "Twilio incoming calls require TWILIO_AUTH_TOKEN and PUBLIC_BASE_URL")
    form = await request.form()
    url = public_base + "/api/voice/twilio/incoming"
    if request.url.query:
        url += "?" + request.url.query
    validator = RequestValidator(token)
    if not validator.validate(url, form, request.headers.get("x-twilio-signature", "")):
        raise HTTPException(403, "Invalid Twilio signature")
    key, agent = eleven_config(agent=True)
    if not form.get("From") or not form.get("To"):
        raise HTTPException(422, "Missing call parameters")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post("https://api.elevenlabs.io/v1/convai/twilio/register-call", headers={"xi-api-key": key},
                json={"agent_id": agent, "from_number": form["From"], "to_number": form["To"], "direction": "inbound"})
        if response.status_code != 200:
            raise HTTPException(502, "ElevenLabs could not register this call")
        content = response.text
        if response.headers.get("content-type", "").startswith("application/json"):
            parsed = response.json()
            content = parsed if isinstance(parsed, str) else parsed.get("twiml", "")
        if "<Response" not in content:
            raise HTTPException(502, "Voice provider returned invalid call instructions")
        return Response(content, media_type="application/xml", headers={"Cache-Control": "no-store"})
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Telephony provider unavailable")


# Production container serves the frontend build and API on one port. Keep this
# last so the static mount never shadows /api.
if (ROOT / "dist").is_dir():
    app.mount("/", StaticFiles(directory=ROOT / "dist", html=True), name="frontend")
