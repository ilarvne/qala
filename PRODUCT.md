# Qala

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

React, TypeScript and Vite frontend; FastAPI and LangGraph backend. The interface uses Assistant UI, actual OpenUI generative components, Phosphor icons and Radix-based controls. CityMap lazily loads one embedded MapLibre/OpenFreeMap renderer with keyless 3D and 2D modes. The main 3D control changes the embedded map. An optional server-side 2GIS Places integration supplies transient source profiles and rating aggregates; it does not render the map or populate the open corpus. Yandex is not a runtime dependency.

## Users

Residents and visitors in Astana looking for a useful nearby activity, a short walk, a family stop, a quiet cafe, a short pre-flight visit, or a suitable evening option. Hackathon evaluators need to try all five scenarios.

## Product Purpose

Turn a user's location, available time, interests and explicit constraints into one to three concrete, source-backed recommendations and a timed mini-route.

## Positioning

A context-aware Astana city companion that connects retrieval over collected POI data with short, actionable explanations, transparent evidence and pedestrian directions. Voice is an optional provider-backed capability.

## Operating Context

User supplies or explicitly shares a location, chooses constraints and asks a question. The interface shows the exact context used, walking and visit times, source provenance and hours uncertainty.

## Capabilities and Constraints

Five scenario presets; English, Russian and Kazakh assistant and control text; group, indoor and accessibility constraints; saved places, session memory and evidence inspection. Some application-shell copy remains English. The default map is the original embedded 3D approach restored by the user's latest instruction: mapped building footprints are extruded using available source heights. It requires no browser API key. This schematic view does not establish architectural accuracy, detailed landmark models or photogrammetry.

All 6,504 ordinary-visible POIs are available through clustered GPU map points and a keyboard-searchable catalogue. A place opens its practical details, available photographs and source profiles without replacing the active route. The one independently confirmed historical closure remains accessible through explicit history and ID lookup.

The conversation has an independent choice of 16 spoken languages. Interface, grounded planner output and dictation retain EN/RU/KK. The actual provider presets and private-session issuance are verified; this does not establish sixteen completed conversations or native pronunciation quality. Translation may preserve and explain only returned facts, constraints and uncertainties.

The embedded 2D/3D button preserves routes, numbered stops, selection and opt-in GPS in one map instance. Flat 2D hides every extrusion and locks pitch at zero. Returning to 3D restores depth inside the app. The button must never become an external provider link. Do not invent landmark geometry or describe generic footprint extrusions as an accurate city model.

Pedestrian geometry and instructions come from the separate Valhalla route service. Before a street route is available, links between stops are dashed and explicitly estimated. Directions can be previewed manually, exported as GPX, or opened in an external Maps app. Optional GPS following begins only after the user enables it; ending navigation stops location updates. Each returned route leg is rounded up to whole walking minutes, then summed with visits and a five-minute buffer. The matching current Assistant UI result, place cards and itinerary share these routed totals and per-stop walking times; older conversation results are not rewritten. A stop at the preceding coordinate has zero walking time. An over-budget route offers a shorter plan before directions can start. Entrances, temporary closures and step-free access are not verified.

Location is never requested on page load. Exact location is not stored in local storage. Saved places are stored on the current device. Unknown hours and unverified sockets remain explicit. AlemPlus and private ElevenLabs credentials are configured and have separately scoped actual API evidence. Provider configuration, session issuance, synthetic microphone input and a physical telephone call are different claims. Quota diagnostics belong to maintenance reports and must not add captions to the interface.

## Brand Commitments

Name: Qala. The user explicitly replaced the earlier green and cream identity with a precision architectural city atlas: white, charcoal, cool slate and cobalt, Geist typography and a focused city-assistant workspace. The accepted visual-world direction is the grounded architectural city model / precision atlas (new-work seed index 5). The latest instruction restores the original embedded footprint 3D approach, with improved clarity and interaction; it does not authorize claims of accurate landmark geometry. Voice is concise, practical, welcoming and honest.

## Evidence on Hand

Hackathon brief at the supplied attachment. The backend owns collected POIs with source provenance. The generated concept is at `artifacts/design/qala-v2-concept.png`; prompts and roles are recorded in `docs/asset-prompts-v2.json`, with imagery in `public/images/v2`. Generated imagery is illustrative, never geographic evidence. The current map decision and verification scope are in `docs/research/embedded-map-restoration.md`. Municipal, Yandex and 2GIS findings remain historical comparison evidence; no example key is copied or reused.

## Product Principles

- Recommendations must fit the user's actual available time.
- Missing evidence stays visible.
- Minimize personal data and give the user control.
- Every recommendation includes a specific action.
- Keep controls direct. Do not add decorative taglines, slogan footers, privacy reassurances, explanatory fine print or floating status captions to fill space. Put necessary factual details and limitations inside the relevant source, route or settings interaction, as recorded in `AGENTS.md`.
- Keep 3D embedded and usable without a provider key. Describe footprint extrusions honestly; do not present them or hand-made patches as an accurate city model. Flat 2D hides every depth layer and locks pitch at zero.

## Accessibility & Inclusion

Keyboard operability, accessible labels and modal titles, reduced motion, mobile responsive behavior, and no assumption of verified wheelchair access.

## Assumptions

The v2 identity replaces the earlier direction by direct user request. After municipal and Yandex evaluation, the user explicitly chose to restore and polish the original embedded 3D view. The current MapLibre map does not depend on those services or their keys. Russian narrated demo and presentation artifacts exist; their export reports define the verified edition. The required accessible YouTube URL and physical telephone testing remain outstanding; the full original goal is incomplete.

## Assistant and data upgrade

The reread brief is retained in `docs/challenge-brief-current.txt`. Automated citywide collection contains 6,505 sourced POIs, 83 licensed photo assignments across 61 places and one source-linked signed rating without opinion text. Unknowns remain explicit; this is not an exhaustive census or a complete commercial review dataset. The assistant supports native editing/versions, actual graph SSE, structured follow-ups, source actions and inline constraints through OpenUI. Consent-only memory can be inspected, edited and deleted. Local cached multilingual neural retrieval has no runtime download; explicit prewarming updates missing document vectors after publication. Current evidence and delivery limits are in `docs/research/media-expansion-2026-10-20.md` and `docs/completion-audit.md`.
