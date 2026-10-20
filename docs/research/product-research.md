# Qala: product and competitive research

Research date: 19 October 2026. Scope: an Astana companion for decisions within the next 30–120 minutes. This is a source review and engineering decision record, not a user study or market-share estimate.

## Finding

Conversational local discovery, travel memory and audio tours already exist. Qala should earn trust through local evidence, explicit uncertainty and deterministic checks on walking time and opening hours. Astana focus and transparent failure handling are the useful wedge. A broad claim that Qala invented AI travel planning would be false.

## Source-backed comparison

| Product | Capability confirmed in official material | What Qala should learn | Qala's narrower proposition |
|---|---|---|---|
| [Google Maps Ask Maps](https://blog.google/products-and-platforms/products/maps/ask-maps-immersive-navigation/) | Conversational questions about nearby places, personalized recommendations, maps, ETAs and actions. Announcement published 12 March 2026. | Natural language discovery must lead to a practical action. Google has a large data and navigation advantage. | Show exactly which Astana POI evidence supports a recommendation and which constraints were checked. No claim of superior global coverage. |
| [Wanderlog](https://wanderlog.com/trip-planner-ai) | AI suggestions, itinerary generation, route optimization, offline access and group collaboration. | A map and itinerary belong in the same experience. Offline planning matters. | Focus on the next hour rather than full holiday organization. The local demo does not need cloud model keys. |
| [Mindtrip](https://mindtrip.ai/) | A personal travel assistant that remembers preferences, weighs travel choices and offers booking assistance. | Memory can reduce repeated input. Users need control over what it remembers. | Explicit opt-in preference storage and deletion, with precise coordinates excluded from persistent preference memory. |
| [VoiceMap](https://voicemap.me/walking-tour-app) and [offline documentation](https://support.voicemap.me/can-i-use-voicemap-offline/) | Human-authored tours, GPS-triggered playback, downloadable map/audio/navigation. | Audio should help people look at their surroundings. Offline audio requires real downloadable assets. | Short recommendations can share the same constrained planner across text, speech and phone. The prototype is not a GPS-triggered navigation product. |
| [izi.TRAVEL](https://www.izi.travel/en/app) and [FAQ](https://www.izi.travel/en/faq) | City and museum audio guides, multiple languages, GPS/QR triggering, authoring platform and offline tours. | Museums and local publishers can supply richer editorial content. | Dynamic nearby decisions from a collected POI corpus, with generated suggestions labeled separately from source facts. |

Absence of a feature from these pages does not prove absence from a competitor. We did not benchmark accounts, mobile apps, current Kazakhstan rollout or commercial APIs. This comparison describes public product claims, not measured quality.

## Astana evidence and conflicts

The [National Museum's own site](https://www.nmrk.kz/en/) states Tuesday–Sunday, 10:00–18:00, with Monday off. Its news also records an exceptional later opening on 13 October. This demonstrates why a normal weekly schedule alone cannot guarantee entry. The application must distinguish regular hours from live availability.

The [Baiterek operator](https://a-vm.kz/en/objects/bayterek/) publishes summer hours of 10:00–22:00 and September–May hours of 10:00–21:00. The [official tourism description](https://visitastana.kz/en/about-city/what-to-see/baiterek-the-main-symbol-of-astana/) describes visitor experience but is less useful for operating hours. Prefer the operator for time-sensitive operational fields and the tourism page for descriptive context.

These sources also use different height descriptions. Qala does not need a height assertion to recommend a short visit. Excluding an irrelevant disputed detail is preferable to selecting a number without context.

The user supplied no POI file. Collection therefore uses an automated OpenStreetMap/Overpass pipeline with source IDs, attribution and collection timestamps. Official venue checks enrich priority records. Unknown sockets, accessibility and hours remain unknown. A collection timestamp records when a page or map record was read, not when staff verified it on site.

## Architecture decision matrix

Scores below are design judgments on a 1–5 scale, not measured benchmarks. Higher is better. The priority order follows the brief: relevance, constraints, explanations, UX, novelty, privacy, completion.

| Option | Evidence control | Time and distance constraints | Works without cloud keys | Delivery simplicity | Decision |
|---|---:|---:|---:|---:|---|
| General LLM with a travel prompt | 1 | 1 | 1 | 5 | Reject. It can invent places, hours or amenities. |
| Live place-search API and LLM | 4 | 4 | 1 | 3 | Useful production enrichment, with usage costs and provider terms. |
| Collected corpus, hybrid retrieval and deterministic planner | 5 | 5 | 5 | 4 | Choose for the local prototype. Source provenance and failure cases stay inspectable. |
| Autonomous browser/booking agent | 2 | 3 | 1 | 1 | Defer. Booking is outside the brief and adds irreversible actions. |

The chosen architecture normalizes context, retrieves candidates, applies hard constraints, builds a feasible route, generates concise language and validates the result. LangGraph makes these stages inspectable. LangChain supplies document and vector-store interfaces. BM25 complements local vectors and multilingual intent aliases. The bundled vector provider uses feature-hashed lexical vectors, not a pretrained neural embedding model. A production upgrade can change the embedding provider without giving the model authority over place facts.

The optional model selects approved evidence focus, introduction style and activity kinds through strict enums. Validation checks IDs, source URLs and category compatibility. The application renders trusted localized text and never promotes arbitrary provider-authored prose. Each displayed POI must exist in the retrieval corpus. Walking estimates use geographic distance with a documented detour factor. They are estimates, not verified pedestrian directions. A routable street graph is a later integration.

## Privacy design

The [ICO geolocation guidance](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/childrens-information/childrens-code-guidance-and-resources/age-appropriate-design-a-code-of-practice-for-online-services/10-geolocation/) recommends attention to location granularity, visible location use and protective defaults, particularly for children. Qala borrows these design principles. This reference does not establish which laws apply in Kazakhstan or certify legal compliance.

Use a chosen landmark by default. Request browser location only after an explicit action. Keep precise coordinates transient. Store preferences only on opt-in, hash the session capability and allow deletion. If a voice provider or LLM is enabled, disclose that selected text goes to that provider. Phone providers necessarily handle call metadata. Production operation requires review of local law, provider contracts and retention settings.

## Research method and search log

Exa was used for eight successful searches across five angles. Requested result counts total 37 candidate results, including duplicates. This is the skill's `sources_reviewed` count, not a claim that 37 full pages were read. Seven official pages were fetched in full-extract mode, followed by the ICO guidance. Search highlights supplied the remaining comparison context. Initial schema-validation failures returned no search results and are excluded. The Exa connector required both `query` and `objective` in this environment.

| Search | Angle | Requested results |
|---|---|---:|
| AI travel itinerary planning: official Wanderlog and Mindtrip | Broad itinerary and memory alternatives | 5 |
| Official Google Maps Ask Maps and immersive navigation | Strongest direct discovery competitor | 5 |
| Official VoiceMap and izi.TRAVEL GPS audio guides | Audio and offline experience | 5 |
| Astana official tourism and venue hours | Local data quality | 5 |
| ICO geolocation and privacy design | Location handling and protective defaults | 5 |
| Official VoiceMap offline app features | Validate audio proposition | 4 |
| Official izi.TRAVEL multilingual audio platform | Validate publisher and language proposition | 4 |
| Astana official operator and museum visitor information | Resolve operational source quality | 4 |

Paraphrased source audit notes used for the comparison are in `official-source-extracts.txt`. Search results change over time. The report records what the sources stated on the research date and avoids unsupported market-size, conversion, latency or accuracy claims.

## Validation before a pilot

Run the five brief scenarios plus unknown hours, Monday closure, explicit wheelchair requirements, airport transfer reserves, prompt injection, unsupported region, memory deletion and no-key voice handling. Measure constraint violations first. Then ask local residents and visitors whether the first suggestion is useful and whether they understand its uncertainty. Establish baselines before making improvement claims.

