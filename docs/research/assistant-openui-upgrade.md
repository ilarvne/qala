# Assistant, OpenUI and task alignment

The supplied Build with AI brief was reread in full for this upgrade. The current copy is `docs/challenge-brief-current.txt`. It asks for an automated POI dataset, a working grounded assistant, context and time constraints, one to three concrete suggestions, a reason and activity for each, accessible UX, uncertainty and privacy. Ratings are conditional on source availability. The additional request asks for real photographs/reviews, stronger RAG, memory and OpenUI.

## Research and implementation

The implementation uses the actual `@assistant-ui/react` runtime and `@openuidev/react-lang` renderer. The official [Assistant UI integration](https://www.openui.com/docs/build-agents/assistant-ui), [component-library documentation](https://www.openui.com/docs/openui-lang/defining-components), [renderer API](https://www.openui.com/docs/openui-lang/renderer) and [action protocol](https://www.openui.com/docs/openui-lang/actions) support registering a small typed vocabulary inside the existing conversation. The application keeps its existing thread, composer and runtime rather than replacing them with an unrelated chat surface.

The planner emits OpenUI Lang after source and constraint validation. The vocabulary contains itinerary, comparison, summary, clarification, preferences and follow-up components. Place components refer only to IDs in that response. React renders trusted source facts from the response; the wire format does not carry HTML, arbitrary styles or new venue facts. No browser tool provider is registered. Unknown IDs cannot select, inspect or save a different place. The small compiler deliberately bounds presentation instead of claiming unconstrained model-authored interfaces.

OpenUI actions focus the existing embedded map, inspect place evidence, toggle saved places, submit contextual follow-ups and apply explicit constraints. Form state is unwrapped from the installed runtime's `{value, componentType}` records before numeric or boolean validation. The source inspector provides real photographs, author/license links, gallery controls, available hours/contacts/accessibility and source-linked ratings. No generated image is presented as a venue photograph.

Assistant UI provides native message editing, resubmission, regeneration, version navigation and cancellation. Completed branch results restore their own plan; a different location, language or departure context isolates prior conversation. Real SSE stages correspond to graph work. There are no fake typing delays. New chat clears the active thread while explicit saved places and consented preference memory remain separate.

## Task-to-evidence mapping

| Requirement | Current evidence |
| --- | --- |
| Automated collection | `scripts/refresh_dataset.py --live`; transactional collection, enrichment, validation and JSON/CSV/GeoJSON export |
| Reproducibility | `--replay`; retained OSM/operator/Commons/signed-review evidence and coverage manifest |
| Real POIs and context | 6,222 mapped records across the Astana administrative boundary; stable OSM IDs and timestamps |
| Photos and ratings | 34 real photo assignments across 22 places, 31 unique cached files; one signed Mangrove rating, with no opinion text |
| Honest missing data | Unknown ratings/reviews/hours/accessibility stay null or unknown; derived category descriptions are distinguishable from the 93 source-backed descriptions |
| RAG and relevance | Eligible-first BM25, LangChain vector retrieval, reciprocal-rank fusion, source identity/geo features and independent plan validation |
| Optional neural retrieval | Prewarmed multilingual MiniLM through FastEmbed/ONNX on two CPU threads; runtime cache loads with network disabled |
| Conversation | Structured interests, exclusions, budgets, group/accessibility/indoor constraints and missing-information questions; no persisted raw conversation |
| Memory | Explicit consent, inspection/editing/deletion, expiry, consent generations and opt-in browser capability persistence |
| Accessible interface | Native keyboard editing and form controls, focus states, mobile input scale/touch targets, semantic comparison table, reduced-motion support |
| Map continuity | Keyless embedded MapLibre 3D/true 2D remains; route, selection and GPS share the same map instance |

## Sources and coverage boundaries

[Data research](poi-data-upgrade.md) records 43 requested Exa results across eight searches, the full source/licensing comparison and actual coverage. This implementation workstream requested another 15 Exa results across three searches: OpenUI integration, reusable open reviews and small multilingual embeddings. Primary-source fetches and installed package inspection followed those searches. Result counts describe discovery effort, not 58 independently endorsed sources.

[Open Reviews technology](https://open-reviews.net/technology/) and the [Mangrove standard](https://mangrove.reviews/standard) provide reusable review records and per-record licensing. One actual Astana rating joined by OSM ID and location was available. Its signature proves record integrity and public-key authorship, not a verified customer visit. Original 70/100 and normalized 3.5/5 values are retained. There is no imported commercial review corpus and no invented rating.

[FastEmbed's supported models](https://qdrant.github.io/fastembed/examples/Supported_Models/) lists the multilingual MiniLM model used here. Explicit prewarming downloads the model once; runtime accepts only the audited cache/model/document identity. Neural verification reports actual observations and a small vector-component comparison, not a general relevance guarantee. The portable fallback is explicitly lexical feature hashing; the optional model-assisted narrative remains bounded and requires its own configured provider.

The collected snapshot covers selected mapped feature classes, not every physical business, recent event or entrance in the city. Most POIs have no reusable photograph, review or source-written description. Power-supply coverage is absent, so a socket cannot be promised. Accessibility tags do not establish an audited step-free street route.

## Verification and original delivery scope

The adapter and OpenUI parser/runtime have reproducible contract checks. Focused real-browser verification covers the built app with real API/SSE, source media, street routing, editing, branches, preferences and mobile controls. Controlled transport and synthetic boundaries are identified in their reports. Visual review uses one desktop/mobile batch, one fix batch and one confirmation; it is not an endless polish loop.

Reports: `artifacts/assistant-adapter-verification.json`, `artifacts/openui-runtime-verification.json`, `artifacts/assistant-upgrade-browser-verification.json`, `artifacts/conversation-rag-evaluation.json`, `artifacts/local-neural-retrieval-verification.json` and `data/dataset-manifest.json`.

The full original hackathon delivery is still incomplete: the existing presentation and video show the earlier interface, live ElevenLabs/telephone execution requires account setup, and no YouTube publication is recorded. This assistant/data upgrade does not claim those separate deliverables are complete.
