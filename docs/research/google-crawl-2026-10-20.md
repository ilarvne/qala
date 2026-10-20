# Google Maps public-card crawl and source integration

Observed 20 October 2026. Exa covered 42 requested and 42 returned search results across five angles, deduplicated to 40 URLs. Search results were discovery, not current Google observations. The usable rows below come from ordinary anonymous browser visits to Google's own pages.

## Actual access results

| Target | Direct browser observation | Primary aggregate counts | Identity check |
| --- | --- | --- | --- |
| Bayterek | 4.6; photograph source link | Not visible | Entity coordinate 5.3 m from local landmark |
| National Museum | 4.6; photograph source link | Not visible | 23.0 m from local museum |
| MEGA Silk Way | 4.7; photograph source link | Not visible | 13.1 m from local mall |
| Cafela, Sarayshyq 9 | 4.2; header also says `Мүлдем жабық` | Not visible | 8.6 m from local cafe |
| Hazrat Sultan Mosque | 4.9; photograph source link | Not visible | 62.2 m from local mosque |
| Botanical Garden | 4.6; photograph source link | Not visible | 43.6 m from local park |

All six selected cards resolved to first-party canonical entity URLs with their own coordinates and hexadecimal entity IDs. These IDs are not represented as Places API `ChIJ…` IDs. Camera viewport coordinates are never substituted for place coordinates. The requested seed and a nearby point are candidate evidence only. Automatic matching requires an exact existing catalogue name/alias, nearby entity coordinates and an unambiguous identity: Bayterek and Cafela pass; four differently transliterated labels remain unassigned for review. No new aliases were invented to force matches.

Google explicitly served its limited Maps version. The Bayterek sidebar also contained Baiterek Coffee, rated 3.8 with a count of 12. Those belong to a different business and are excluded from the landmark aggregate. The parser scopes its rating to the primary heading's adjacent header, rather than scanning all sidebar text.

Normal HTTP requests to the Maps home page and two search URLs returned 200 with a JavaScript bootstrap, without usable place-specific JSON-LD. The HTTP parser returns no rows for that shell. The registered Places endpoint was also tested directly: an unauthenticated `POST /v1/places:searchText` returned 403 `PERMISSION_DENIED`, explicitly requiring caller identity. No guessed key, browser key, private endpoint or alternate identity was used.

## A useful official embedded source view

The ordinary Google Maps **Share → Embed a map** control generated an iframe for Botanical Garden without an API key. The iframe was tested inside a local HTML page, and its real map rendered with Google's attribution and controls. It showed 4.6 and the native link label `6,772 пікір (жаңа қойындыда ашылады)`. The native counter is preserved separately: it is not silently converted to a written-review count or the API's `userRatingCount` field. The main card's count fields remain unknown.

Google documents this consumer sharing workflow in [Maps Help](https://support.google.com/maps/answer/144361?hl=en). This differs from the developer [Maps Embed API](https://developers.google.com/maps/documentation/embed/embedding-map), whose `/embed/v1/…` interface requires a key. The exact UI-generated iframe is retained rather than constructing an undocumented `pb` payload. The standalone iframe URL correctly says that it must be loaded inside an iframe.

This is a viable optional source-view interaction, not a replacement for Qala's selected MapLibre map. Loading it causes browser requests to Google and its map resources; an implementation should load it only when the user opens that provider source, retain provider attribution and the original interactive widget, and avoid sending chat or preference data. No Qala runtime or UI was changed in this workstream. No photos or review prose were extracted from the widget.

## Distinct website and API requirements

The [Google Maps end-user terms](https://www.google.com/help/terms_maps/) prohibit mass downloading and bulk content feeds. Their separate mapping-dataset clause concerns creating or augmenting a mapping-related dataset for a service that substitutes for, or is substantially similar to, Google Maps. This is a provider-use restriction, not a blanket assertion that every public factual observation is legally unavailable. These bounded observations remain evaluation evidence, and none was imported into the reusable catalogue.

For an authorized integration, [Places API policies](https://developers.google.com/maps/documentation/places/web-service/policies) separately govern storage exceptions, Google-map display, no-map branding, third-party attribution and original photo/review links. Place IDs have an explicit storage exception; this does not make all returned content exportable. Those API requirements are not presented as the website's robots policy.

The [Place reference](https://developers.google.com/maps/documentation/places/web-service/reference/rest/v1/places) limits a response to at most five relevant reviews and ten photos. An API key is therefore not an unlimited review crawler. [Photo documentation](https://developers.google.com/maps/documentation/places/web-service/place-photos) also requires obtaining current photo resource names and retaining required author attribution; names can expire and must not be cached. Google photo source URLs in this audit are evidence links, not licensed local assets. The [Business Profile review API](https://developers.google.com/my-business/content/review-data) requires OAuth/account-location access; it is not an anonymous citywide review export.

## Operating-status conflict

`osm-node-5936638686` is currently recommendable in the local catalogue, with no hours, website or phone and an OSM edit from August 2023. Google's matching Cafela card reports permanent closure. A historical directory identified `cafela.satu.kz`, but a current normal HTTPS visit redirects to the generic Satu marketplace homepage and provides no operator statement. Other discovered Cafellini/Coffella venues have different names and addresses and were rejected. There is **no independent operator confirmation**, so this is an unresolved source conflict requiring re-verification, not a confirmed closure or a silent catalogue edit.

## Reproducibility and evidence

- `scripts/providers/google.py`: semantic public-JSON-LD parser plus a narrowly scoped visible-card parser. It does not decode Maps initialization arrays.
- `scripts/crawl_google_public.py`: six explicit named seeds maximum, ordinary HTTP preflight, longest-rule robots handling, browser DOM extraction and stop-on-denial. It records 401/403/429, CAPTCHA or a consent gate and stops the provider without switching transport or identity. Raw bodies, review texts and image bytes are not saved.
- `backend/tests/test_provider_google.py`: 26 passing cases after the offline parser follow-up, including nested-business contamination, non-finite data, viewport confusion, robots specificity, HTTP denial without browser fallback, browser-challenge termination, a wrong business within ten metres of the requested seed, unknown/cached acquisition times and browser document denial after a successful HTTP preflight. The original frozen acquisition status retains its earlier 18-test scope.
- `artifacts/provider-crawl/google/rows.json`: six original public-card observations, all `evaluation_only`.
- `browser-probes.json`, per-place `*-visible.json`, three card screenshots and `http-probes.json`: actual acquisition evidence, separate from Exa discovery.
- `official-share-embed.json`, `embed-proof.html`, `embed-frame-verification.json`, `embed-frame-proof.png`: UI-generated official widget and successful rendered-source proof. `embed-observation.json` is a separate observation of the same park, not a seventh unique place.
- `quality-conflicts.json`: exact Cafela header, matching local identity, source URL and unresolved operator verification.
- `research-searches.json`: requested/returned Exa totals and deduplicable result URLs.
- `cli-smoke/`: a fresh one-seed live run of the bounded browser CLI, with HTTP 200, correct entity identity and no downloaded media.

Run from the project root after installing Agent Browser:

```bash
python scripts/crawl_google_public.py --browser-cli /path/to/agent-browser --limit 6
.venv/bin/python -m pytest backend/tests/test_provider_google.py -q
```

The original Google requirements and provider source links should be reviewed again before any production redistribution, paid API use or automatic ingestion. This audit changes no catalogue rows, recommendations, map provider or user account state.

The final network-free follow-up separates HTTP preflight status from the browser's navigation response status. Browser 401/403/429 ends acquisition even if the body has no CAPTCHA keywords; absent/zero navigation status remains unknown. All offline parsers require supplied acquisition metadata to establish freshness: parsing cached HTML without it returns `observed_at=None` and a warning. No extra live Google request was needed for these fixes.
