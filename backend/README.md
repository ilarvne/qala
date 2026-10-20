# Qala backend

Run from the repository root:

```bash
uv sync --frozen
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --no-access-log
uv run pytest -q
```

Python 3.11+ is supported. The checked-in `uv.lock` pins the tested environment. No API key is needed for the working source-grounded demo. `/docs` exposes interactive OpenAPI documentation. A built root `dist/` is served on the same port.

## What runs

The real LangGraph graph executes `understand_context → external_context → hybrid_retrieval → provider_rerank → budget_route → validate_plan → grounded_response → privacy_memory`. Conditional edges route insufficient results or infeasible budgets through `no_match`; explicit calendar requests use `event_response` and return sourced event metadata without inventing a timed POI route. This is a bounded planning graph. The reranking node retains local ordering when its provider is disabled or unavailable.

The real LangChain `InMemoryVectorStore` retrieves `Document` objects with source IDs. The portable default uses 512-dimensional feature hashes of multilingual lexical tokens and explicit interest aliases; these are **not neural semantic embeddings**. Opt-in `QALA_EMBEDDINGS=local` uses a prewarmed 384-dimensional multilingual MiniLM model through FastEmbed on CPU, without an API key or runtime downloads. Retrieval first filters geographically and by category, exclusions, indoor, wheelchair and public-access metadata, so remote matches cannot crowd local candidates out of vector top-k. Eligible BM25 and vector rankings are combined using reciprocal rank fusion (0.35), interest overlap (0.22), geographic proximity (0.28) and mapped-name match (0.15). Schedule and cumulative transit/visit constraints are applied during planning and independently checked before composition. Query-local reports expose the eligible corpus, rejection counts, ranks and matching interests without sharing mutable request state. `QALA_EMBEDDINGS=openai` opts into actual OpenAI neural embeddings; a provider failure falls back to local vectors. The health response identifies the active embedding mode.

Routes contain one to three stops. A coffee-only request gets one suitable café. Cumulative transit, estimated visits and a five-minute buffer must fit the budget. Walking links use Haversine distance × 1.3 and 65 m/min, or 50 m/min for accessibility requests. The frontend separately requests actual Valhalla street routes and checks the revised total before navigation. Neither method certifies step-free streets.

The external-context node fetches cached Open-Meteo forecasts for fixed Astana city coordinates and the official Astana Venue Management calendar concurrently. Weather is matched to the planned window and can softly prefer indoor venues, preserving explicit indoor/outdoor constraints. Source details expose the interval, retrieval time and CC BY 4.0 attribution. The free weather service is noncommercial; commercial deployment needs an appropriate plan. Calendar entries include only published titles, dates and source URLs; absent venue, showtime and tickets remain unknown. The calendar covers one operator, not all city events. Set `QALA_WEATHER=off` and `QALA_EVENTS=off` for offline operation. Failures preserve ordinary POI planning. See [context research](../docs/research/agent-context-2026-10-20.md).

For mixed requests, planning prioritizes an uncovered named venue interest before adding incidental stops. An architecture walk with coffee reserves feasible time for a landmark and café instead of spending that café time in another nearby garden. Validation independently derives `context.fulfilled_interests` and `context.unfulfilled_interests` from original source records. A tight budget may yield partial coverage; these fields do not claim that every requested activity fits.

Hours use a conservative subset of OSM `opening_hours`: daily schedules, day ranges, overnight schedules and `24/7`. Unparsed schedules return `unknown`. Results are `listed_open` or `listed_closed`, never a live guarantee. Every occupied minute of a visit must fit a parsed schedule, including any midday closure. Operator-verified National Museum hours exclude Mondays; Baiterek uses the operator's seasonal schedule. These facts carry separate `hours_source` and `description_source` URLs and observation timestamps.

Night requests and plans starting from 22:00 to 06:00 consider only places with a matching listed schedule. Lighting, nighttime access and transport stay unverified; the response says so rather than inventing an event or safe path.

Preflight requests require an explicit `airport_transfer_minutes` estimate. Without one, the assistant asks for it and gives no itinerary. With one, it deducts that estimate plus a minimum 90-minute airport reserve. Travellers still need to check their airline's own formalities; the 90 minutes is a planning floor, not airline advice.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Dataset, real mode and configured integration flags; configuration is not a live verification |
| GET | `/api/pois?category=park` | Normalized genuine POIs and collection metadata |
| GET | `/api/integrations` | Configured capabilities, actual observations, source links and provider restrictions |
| GET | `/api/events?starts_at=2026-10-28T14:00:00%2B05:00&days=14` | Official dated calendar metadata; no invented walking stops |
| POST | `/api/recommend` | Contextual, source-backed recommendation and route |
| POST | `/api/chat` | Same planner with bounded structured conversation context |
| POST | `/api/chat/stream` | Actual graph-stage SSE followed by the complete result |
| GET | `/api/memory/{session_id}` | Read a capability-protected preference record |
| POST | `/api/memory/{session_id}` | Consent-protected preference edit with optional generation guard |
| DELETE | `/api/memory/{session_id}` | Delete the preference record |
| POST | `/api/voice/transcribe` | AlemPlus multipart audio dictation; `file`, `language` (`en`/`ru`/`kk`) |
| POST | `/api/voice/speech` | ElevenLabs MP3 TTS; `{text, language}` |
| POST | `/api/voice/session` | Server-generated private-agent signed URL; `{language}` |
| POST | `/api/voice/tools/recommend` | Authenticated ElevenLabs server tool |
| POST | `/api/voice/twilio/incoming` | Signed Twilio incoming webhook → ElevenLabs TwiML |

```json
{
  "message": "A short architecture walk and coffee",
  "location": {"lat": 51.1282, "lon": 71.4304, "label": "Baiterek · simulated"},
  "duration_minutes": 75,
  "interests": ["culture", "coffee"],
  "language": "en",
  "accessible": false,
  "indoor": false,
  "group_size": 1,
  "starts_at": "2026-10-20T14:00:00+05:00",
  "remember": false
}
```

The response contains `message`, `recommendations`, `route`, `context`, `trace`, `mode`, `sources`, `dataset` and `elapsed_ms`. Each recommendation has an OSM ID/URL, coordinates, localized name, category, why, suggested action, estimated visit/walk time, schedule uncertainty and null unknown ratings. Generated actions carry `action_origin`; they are not event listings. `context` explains filters, missing data and memory. Numeric coordinates use `lat/lon`; map route coordinates use GeoJSON order `[lon,lat]`.

## Conversational assistant and OpenUI

`POST /api/chat` accepts the same validated request as `/api/recommend`. Send the previous response's `conversation` on the next turn. It contains only bounded canonical interests, excluded IDs/categories, the previous one to three IDs, time, indoor/accessibility/group constraints, optional walking cap and airport context. It cannot contain venue facts or arbitrary assistant prose. The server resolves every ID against the current corpus; invented IDs are ignored. Nothing in this client-held context is stored as chat history.

Explicit message changes take precedence over previous conversational constraints. For example, “Coffee nearby” → “Only indoors, make it 40 minutes” keeps coffee, enforces indoor venues and shortens the total budget. “Show alternatives” excludes previous IDs; “A park instead” replaces the category; “Start over” drops previous context. “Keep walking under 10 minutes” caps cumulative walking while preserving the visit budget. Negative categories such as “no museums” stay exclusions. Parsing supports bounded English/Russian/Kazakh phrases and explicit structured filters; it is not a general language-understanding claim. A numeric answer to a pending airport-transfer question resolves that estimate without replacing the departure deadline.

`POST /api/chat/stream` emits real graph-boundary server-sent events:

```text
event: status
data: {"stage":"retrieve"}

event: status
data: {"stage":"rank"}

event: status
data: {"stage":"validate"}

event: status
data: {"stage":"compose"}

event: result
data: { ...same complete recommendation response... }
```

An abstention may skip stages; no fake delay or fabricated token stream is used. Errors are sanitized, responses are not cached, and SSE is excluded from compression. The JSON response adds `conversation`, actionable `clarifications`, localized `followups`, query-local `retrieval` diagnostics and a trusted `openui` program. OpenUI references only IDs from that response and registered components/actions. Retrieved text cannot generate HTML, arbitrary component names, scripts or new facts. Comparisons show planned stops, not independent alternative routes.

Culture is no longer treated as one interchangeable visit type. Architecture and walking queries select mapped landmarks, monuments, memorials, public art, fountains and similar public stops; a cinema or library cannot become a twelve-minute landmark visit. A library request uses a thirty-minute reading visit and asks about public entry. Explicit cinema/theatre requests reserve a conservative 120-minute visit and ask for actual programme/running time; a short budget produces an actionable duration clarification. Restaurant, ice-cream, food-court, exercise-equipment, pool and pitch actions follow their actual source type. The optional model selects only the appropriate trusted action vocabulary. Family context excludes adult nightlife and survives a category change until explicitly cleared. Default introductions state the actual stop count and time limit without a marketing tagline.

Every recommendation now carries available normalized `photos`, `image`, `rating`, `rating_count`, `rating_source`, `reviews`, `review_count`, `address`, `contact`, `amenities` and `accessibility`. Missing facts remain null or empty. Image authorship/licensing/source metadata stays attached; ratings are copied from actual source records, never generated by the agent. A listed accessibility tag is not a step-free route guarantee.

The inventory API supports `GET /api/pois?q=National&category=museum&limit=100&offset=0`, returning `pois`, `total`, `limit`, `offset` and original dataset metadata. Omit pagination for the backwards-compatible full inventory. Responses omit raw OSM tags and use HTTP gzip when requested. `GET /api/pois/{id}` returns a single complete normalized source record or 404.

`POST /api/memory/{session_id}` updates inspected preferences without generating an itinerary. It requires explicit `consent:true` and accepts bounded interests, language, duration, indoor/accessibility, walking cap and excluded categories. Only recognized interests/categories are saved. Every memory response includes `generation`; current clients send it as `memory_generation` on planning requests. The store checks both the request-start snapshot and that client-held consent epoch. A stale queued planning request beginning after deletion cannot silently grant consent again. The explicit preference POST also accepts `memory_generation` and returns HTTP 409 if it is stale, so a queued old save cannot recreate deleted preferences. Current clients send `use_saved_preferences:false` after local revocation or a failed deletion; the server still captures the consent epoch but does not apply that stored profile to the plan. `context.preferences_applied` reports actual profile use separately from storage presence. A fresh explicitly opted-in request using the new epoch may save. An edit advances the same consent generation used by deletion, preventing an older in-flight request from overwriting the edit. This endpoint never adds a location. Existing `GET` and `DELETE` memory endpoints remain available; enabling request-level `remember` still saves only minimized preferences and coarse location. No raw message or full graph checkpoint is retained.

Reproduce the focused quality report with:

```bash
uv run python scripts/evaluate_conversation.py
```

The report at `artifacts/conversation-rag-evaluation.json` contains nine manually source-labelled multilingual entity lookups, contextual adaptation cases and a context-removal ablation. Its measured scores apply only to this inspectable regression set, not all city queries or production relevance. The broader scenario evaluation remains `scripts/evaluate.py`.

## Keyless local neural retrieval

Install the optional locked dependency and explicitly prepare the public model once:

```bash
uv sync --frozen --extra neural
uv run --extra neural python scripts/prewarm_embeddings.py
QALA_EMBEDDINGS=local uv run --extra neural uvicorn backend.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

The selected model is `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`: 384 dimensions, Apache-2.0, listed by [FastEmbed's primary model documentation](https://qdrant.github.io/fastembed/examples/Supported_Models/). The prewarm command is the only path that downloads weights and computes document embeddings. It limits ONNX Runtime to two CPU threads and writes a resumable SQLite float32 vector cache. Each vector is keyed by document SHA-256 plus the actual tokenizer/ONNX file fingerprint, so changed text or model files cannot silently reuse an older embedding. Repeated identical POI documents share cached vectors.

The API checks the corpus cache before loading the model, reads document vectors from SQLite, and embeds only new queries on CPU. It supplies both `local_files_only=True` and the exact cached model directory. Missing dependencies, weights, stale documents or invalid cache entries produce the explicit health mode `local-feature-hash-cache-unavailable` or a provider-fallback mode; no network download or full-corpus computation happens at startup. A query-time model error leaves lexical/metadata retrieval active and is reported in query diagnostics. The portable default and offline acceptance scripts use hash vectors and need no model cache.

Cache files live under ignored `.local/embeddings` and are excluded from the submission archive. On another machine, run the explicit prewarm command; do not mistake the shipped hash fallback for a downloaded neural model. Models and caches can be removed to return to the portable default. The application still uses the same source-grounding, hard constraints and final validation in every embedding mode.

Reproduce the actual local model/network guard and semantic component comparison:

```bash
uv run --extra neural python scripts/evaluate_local_embeddings.py
```

This report blocks runtime sockets while loading the cached model and running real queries, then compares its vector component with feature hashes on 11 manually labelled implicit-language probes. The actual cached-model run made zero runtime network attempts, loaded the full cached corpus in about 3.6 seconds and had a median vector query time of 118 ms on this machine. Mean vector precision@5 was 0.4545 versus 0.0909 for feature hashes across the 11 probes. These are component diagnostics; the small set is not a comprehensive multilingual relevance guarantee or end-user accuracy score. It also runs the complete hybrid retrieval path with geographic/category constraints.

## Environment

Set server credentials in the root `.env`; never add them to a frontend variable.

| Variable | Required for |
| --- | --- |
| `QALA_LLM_PROVIDER` | `alemplus`, `openai`, or `local` to disable cloud selection; if unset, prefer configured AlemPlus, otherwise OpenAI |
| `ALEMPLUS_API_KEY`, `ALEMPLUS_MODEL` | AlemPlus presentation selection; model defaults to `alemllm` |
| `QALA_RERANK_PROVIDER` | `alemplus` (default) or `none` to retain local rankings |
| `ALEMPLUS_RERANK_KEY` | Optional bounded cloud reranking with model `reranker` |
| `ALEMPLUS_EMBED_KEY` | Explicit two-text verification probe with `text-1024`; does not select the runtime city index |
| `ALEMPLUS_STT_KEY`, `ALEMPLUS_STT_KK_KEY` | Explicit audio dictation with `speech-to-text` or dedicated `speech-to-text-kk` |
| `OPENAI_API_KEY` | Optional LLM-assisted presentation selection |
| `OPENAI_MODEL` | Optional; defaults to `gpt-4.1-mini` |
| `QALA_EMBEDDINGS` | `hash`/unset: portable lexical vectors; `local` or `fastembed`: prewarmed CPU neural model; `openai`: configured remote neural embeddings |
| `QALA_EMBEDDING_CACHE` | Optional local model/vector cache path; defaults to `.local/embeddings` |
| `OPENAI_EMBEDDING_MODEL` | Optional; defaults to `text-embedding-3-small` |
| `ELEVENLABS_API_KEY` | TTS and conversational voice |
| `ELEVENLABS_VOICE_ID` | TTS voice |
| `ELEVENLABS_MODEL_ID` | Optional TTS model; defaults to `eleven_v3`, which supports Kazakh |
| `ELEVENLABS_AGENT_ID` | Existing private ElevenLabs conversational agent |
| `ELEVENLABS_AGENT_MODEL_ID` | Conversation provisioning model; defaults to `eleven_v4_turbo` with16 spoken-language presets from `data/voice-languages.json`. UI/planner and dictation retain EN/RU/KK. `eleven_v3_conversational` is an explicit account-compatible alternative |
| `ELEVENLABS_TOOL_ID`, `ELEVENLABS_SECRET_ID` | Optional existing resource IDs; provisioning writes these for repeatable updates |
| `VOICE_TOOL_SECRET` | Strong random secret configured on the agent's server tool |
| `TWILIO_AUTH_TOKEN` | Validate custom incoming Twilio webhooks |
| `PUBLIC_BASE_URL` | Exact public HTTPS origin used by Twilio, without trailing slash |
| `QALA_MEMORY_PATH` | SQLite path; defaults to `.local/preferences.sqlite3` |
| `CORS_ORIGINS` | Comma-separated trusted frontend origins |

The selected LLM receives selected source IDs/URLs, categories, estimated distances/timings and canonical interests, not exact user coordinates, raw messages or session IDs. It selects only enum values for introduction style, evidence focus and category-appropriate action kind. Schemas forbid extra prose fields; the backend revalidates every result, requires exact selected IDs/source URLs and validates each action against its POI category. Every visible introduction, reason and action is rendered from trusted localized templates and retrieved numeric values. Arbitrary model-written text never enters the response. Valid selections use mode `llm-assisted`; invalid or unavailable selections fall back to `grounded-demo`. Real LangChain retrieval and optional neural embeddings remain active independently of this presentation boundary.

## AlemPlus services and verification

Adapters use the documented [AlemLLM](https://doc.alem.ai/services/alemllm.html), [embedder](https://doc.alem.ai/services/embedder.html), [reranker](https://doc.alem.ai/services/reranker.html), [speech](https://doc.alem.ai/services/speech.html) and [Kazakh speech](https://doc.alem.ai/services/speechkaz.html) endpoints at `https://llm.alem.ai/v1`, with separate server-side bearer keys. The actual account accepted all five model/auth checks. `artifacts/alemplus-live-verification.json` records three real multilingual LLM/rerank graph requests, a two-text 1024-dimensional embedding proof, and transcription of generated English and Kazakh speech fixtures. These prove those provider requests; they do not establish general speech accuracy or a physical phone call.

The account rejected OpenAI-compatible strict `json_schema` output with HTTP 400. AlemLLM therefore uses LangChain JSON mode with an explicit schema in the system prompt, followed by the same strict local Pydantic and source/action validation as other providers. This is a transport compatibility choice, not reliance on unconstrained generated prose. Requests have bounded timeouts and no automatic LLM retries; failures use the local grounded response. `QALA_LLM_PROVIDER=alemplus` selects this provider even if an unrelated OpenAI key is present. Set `QALA_LLM_PROVIDER=local` and `QALA_RERANK_PROVIDER=none` for offline operation.

Cloud reranking sees at most sixteen public POI texts (900 characters each) plus canonical interests. It never receives the raw user query, exact user coordinates or memory capability. Response indices must form a valid unique permutation with finite scores; it can only reorder already filtered candidates. Access, exclusions, listed schedules and cumulative route budgets remain local constraints. A timeout, malformed response or provider error retains the local ranking.

The live city index intentionally remains the cached local 384-dimensional MiniLM corpus with local CPU query inference. The separate `text-1024` proof sent one public museum description and one generic query; it did not bulk-embed the 6,222 places or silently replace the index. Optional `QALA_EMBEDDINGS=openai` is a distinct explicitly selected mode that discloses public POI documents and the search text, including the user message, to that embedding provider.

`POST /api/voice/transcribe` sends an explicitly uploaded audio file to AlemPlus. English/Russian use `speech-to-text`; Kazakh uses its separate key and `speech-to-text-kk` model. Uploads are limited to eight MiB and supported audio MIME types, use a fixed provider filename, and return `Cache-Control: no-store`. The application does not log or retain the audio or transcript; provider-side retention is governed by that service. Transcripts populate dictation and follow the same planner boundary as typed messages. Provider errors return sanitized text without raw bodies or secrets.

Browser WebM/Opus, Ogg and Safari MP4 require FFmpeg on the server; the Docker image installs it. The provider rejected actual WebM with HTTP 400 although MP3 worked. These browser containers are now decoded through pipe-only FFmpeg protocols into canonical 16 kHz mono WAV in memory, with a 61-second audio limit, one decoder thread and a ten-second conversion deadline. Timeout/cancellation kills and reaps the process; input filenames, stderr, audio and transcripts are not retained. MP3/WAV uploads keep their direct path. `artifacts/browser-dictation-compatibility.json` records an actual before/after check using the same nonpersonal Russian speech fixture: upstream 400 before normalization, 200 and recognized expected words after it.

Health distinguishes configured services, the active index and successful requests observed in the current process. A previous verification report does not make a newly started process's `live_verified` flag true. Run the explicit verification script only when authorized to make real provider requests:

```bash
uv run python scripts/check_alemplus.py
```

The default test fixture blanks private keys before test-module imports and disables paid providers. Unit tests use isolated fixture credentials and intercepted HTTP clients; offline evaluations also disable cloud LLM/reranking explicitly. No private key, raw transcript or raw provider error body is included in verification artifacts.

## ElevenLabs and telephone setup

The repeatable setup CLI replaces manual agent/tool creation. It uses the current official [agent API](https://elevenlabs.io/docs/eleven-agents/api-reference/agents/create), [workspace tools API](https://elevenlabs.io/docs/eleven-agents/api-reference/tools/create), [workspace secret API](https://elevenlabs.io/docs/eleven-agents/api-reference/workspace/secrets/create), and [published OpenAPI schema](https://api.elevenlabs.io/openapi.json). Review the sanitized offline plan first; this command needs no credentials and makes no provider requests:

```bash
uv run python scripts/provision_elevenlabs.py --public-base-url https://your-qala.example.com
```

Inspect `artifacts/elevenlabs-plan.json` and the template `backend/elevenlabs-agent.json`. The plan contains placeholder secret references only. It names a private, signed-URL agent, authenticated webhook tool, a verified public-landmark reference generated from `data/pois.json`, and English/Russian/Kazakh presets. The prompt binds browser `{{context}}` and `{{language}}`, treats them as untrusted preference hints, and requires explicit location confirmation. Only the language can be overridden by the browser; its prompt and tools cannot. Telephone callers receive questions when no browser context exists.

Set `ELEVENLABS_API_KEY` and an accessible `ELEVENLABS_VOICE_ID` in the root `.env` or server environment. For local development, start an HTTPS tunnel to port 8000 and use that tunnel's **origin** as `PUBLIC_BASE_URL`. A loopback URL cannot receive provider webhooks. Then provision and restart the backend so it reads the generated settings:

```bash
uv run python scripts/provision_elevenlabs.py --public-base-url https://your-qala.example.com --apply
# Restart the Qala backend, then verify real provider auth and the public tool.
uv run python scripts/provision_elevenlabs.py --check
```

`--apply` creates or updates a workspace secret, webhook tool and agent. `--agent-id` adopts an existing agent; attached Qala tools are reused, and unrelated attached tool IDs are preserved. Explicit `ELEVENLABS_TOOL_ID`/`ELEVENLABS_SECRET_ID` or the private receipt also reuse existing resources. The CLI persists each returned ID immediately in `artifacts/private/elevenlabs-provision-state.json` and atomically updates only the managed root `.env` variables with mode `0600`. A missing `VOICE_TOOL_SECRET` is securely generated and saved before cloud mutations. The API key is read, never printed or copied into the plan. Keep the receipt private; it is excluded from the submission archive. If a creation response is lost, the receipt stops automatic retries to avoid duplicates: inspect the provider workspace and set the indicated resource ID before retrying. Use a separate receipt and environment file for a second deployment.

The conversation uses `eleven_v4_turbo` and16 explicit spoken-language presets: en, ru, kk, de, fr, es, zh, ar, tr, hi, ja, ko, uk, it, ky and az. The browser's conversation-language picker is independent of the EN/RU/KK interface, planner and dictation. The agent translates confirmed caller constraints for the grounded planner, then translates only returned facts and uncertainties. [Actual provider read-back](../artifacts/voice-language-configuration-verification.json) verifies these presets and signed-session issuance, rather than sixteen completed conversations or pronunciation quality. [Language research](../docs/research/multilingual-voice-2026-10-20.md) records current official sources and API model metadata. `--agent-model-id eleven_v3_conversational` remains an explicit alternative subject to account access. The [language-detection system tool](https://elevenlabs.io/docs/eleven-agents/customization/tools/system-tools/language-detection) switches among configured presets. Both input and output use `ulaw_8000` for the custom Twilio path. Provisioning disables audio recording, requests zero-day transcript retention, limits conversations to ten minutes, caps daily conversations at30 and concurrency at two, and disables bursting. A deployer must verify its account accepted these settings. [Authentication](https://elevenlabs.io/docs/eleven-agents/customization/authentication) and [privacy](https://elevenlabs.io/docs/eleven-agents/customization/privacy) describe provider behavior. Quota diagnostics remain in maintenance reports; they must not create interface captions.

`--check` makes actual HTTP requests: it reads the private agent/tool configuration, obtains (but never prints) a signed session URL, and sends one authenticated, nonpersistent planning request to the deployed webhook. It does **not** start a microphone session, buy a phone number, change a billing plan or place a call. A passing check proves those configuration and planner boundaries; `conversation_live_verified` and `phone_call_live_verified` remain false until an actual browser conversation and phone call are tested. No provider call or phone test has been performed by the checked-in offline tests.

Manual setup remains available:

1. Create a private ElevenLabs conversational agent. Enable signed URL authentication. The browser requests its temporary URL from this backend; API keys never leave the server. Use a voice/model whose language coverage includes the requested language. TTS `eleven_v3` supports English, Russian and Kazakh; `eleven_multilingual_v2` does not list Kazakh. See [agent authentication](https://elevenlabs.io/docs/eleven-agents/customization/authentication) and [model language support](https://elevenlabs.io/docs/overview/models).
2. Add a server webhook tool named `recommend_city_walk`, POST `${PUBLIC_BASE_URL}/api/voice/tools/recommend`, with header `X-Qala-Tool-Secret` set to the same strong secret as `VOICE_TOOL_SECRET`. Import the request/response schema from `/openapi.json`; `RecommendRequest` is the tool body. Restrict tool URL access in your deployment and do not put the secret in the tool description.
3. Instruct the agent: “Ask the caller for a named starting landmark, available minutes, language and constraints. Resolve a landmark only from verified coordinates in the Qala dataset. Never assume the caller's current location. Call the tool with explicit location. Read at most three returned places, reasons, estimated times, actions and uncertainty. Never invent events, sockets, quietness, opening guarantees or accessibility. Ask for a live airport-transfer estimate before planning preflight. Never remember caller data or phone numbers.” For known landmarks, provide only verified `data/pois.json` coordinates through the agent's knowledge base. If the caller's landmark is unresolved, ask a clarification instead of fabricating coordinates.
4. The recommended phone path is ElevenLabs' [native Twilio integration](https://elevenlabs.io/docs/agents-platform/phone-numbers/twilio-integration): import a Twilio number, assign the configured agent and set the authenticated server tool above. Calls then use exactly the same grounded planner. This requires an actual Twilio number/account and provider credits.
5. Existing enterprise VoIP can use [SIP trunking](https://elevenlabs.io/docs/agents-platform/phone-numbers/sip-trunking). Configure the trunk, authentication and routing in the ElevenLabs console, assign the same agent and tool. This repository does not provision a SIP account or trunk.
6. For full control of an existing Twilio webhook, set it to POST `${PUBLIC_BASE_URL}/api/voice/twilio/incoming`. Configure the ElevenLabs agent's input/output as μ-law 8000 Hz. This endpoint validates `X-Twilio-Signature` with Twilio's SDK against the exact public URL, then calls the official [register-call endpoint](https://elevenlabs.io/docs/eleven-agents/api-reference/integrations/twilio/register-call) and returns TwiML. Forwarded headers are not trusted to build the signed URL. The custom register-call approach does not support call transfer.
7. Browser microphone sessions, voice charges and real calls require provider testing after credentials are added. The health API deliberately reports `live_verified: false`; it never treats an environment variable as a successful call.

## Data and privacy

```bash
uv run python scripts/collect_pois.py
uv run python scripts/collect_pois.py --input data/raw/astana-overpass.json
```

The collector runs an explicit geographic Overpass query, retains genuine OSM IDs/version/update time, stores raw source and SHA-256, filters to supported categories and adds conservative derived tags. It atomically replaces the normalized snapshot only after a valid collection. Two allowlisted venue operators are fetched for source-checked enrichment, with raw HTML retained; failed fetches do not fabricate replacement facts. OSM-derived data is ODbL 1.0; show [© OpenStreetMap contributors](https://www.openstreetmap.org/copyright) wherever used. Way/relation coordinates are bounding-box centers and may differ from entrances.

No raw messages, phone numbers or precise user coordinates are stored in the preference DB. A client-generated cryptographically random session ID is a bearer capability; only its SHA-256 digest is stored. `remember:true` saves interests, language, duration, accessibility, indoor preference and location rounded to 0.01° (about one kilometre) for 30 days. Expired rows are purged at access. Deletion immediately removes preferences and increments a hashed consent-generation tombstone retained for at most 30 days. Atomic SQLite snapshot/compare-and-save checks prevent an already-running recommendation from restoring deleted preferences. A fresh, explicitly opted-in request after deletion may save again. The tombstone contains only the session hash, generation and expiry, not preferences or location. Full LangGraph state is deliberately not checkpointed because it contains precise request coordinates. Use `--no-access-log`, HTTPS and a suitable reverse-proxy policy so URL capabilities do not appear in request logs. Existing backups or infrastructure logs need their own retention controls.

The built-in per-process limiter caps recommendation and voice calls. This hackathon deployment has no multi-user account authentication, distributed limiter, verified step-free routing, guaranteed realtime POI availability or live event/weather feeds. Add those controls before a public multi-tenant launch.
