# 2GIS Platform Places API: current contract and bounded diagnostics

Checked 20 October 2026 using current primary documentation and legal pages. Three Exa searches requested and returned 24 results; direct official-page reads were used to distinguish the Platform offer from older consumer API rules. No blocked public organization cards were revisited, and this workstream made no authenticated API requests.

## What the current Platform offer actually says

The [combined Directory/Cartographic WebAPI offer](https://law.2gis.ru/offer-license-agreement-webapi) is dated **9 October 2026**. Its definitions explicitly include Places API; clauses 2.5.1–2.5.2 provide for documented API requests and displaying returned Products in the user's application. Clause 3.1 restricts extracting, retaining and reusing Products or information from them outside agreed uses and says caching is not provided. I found no 60-second exception.

I found no simultaneous-third-party-map prohibition or explicit incorporation of the older Directory API rules in this offer's body. The page's general legal navigation links to other agreements; that is not itself an incorporation clause. This finding does **not** establish that an individual key's accepted account/invoice terms have no additional conditions. Clauses 2.1–2.4 describe that contractual scope; 11.6 also preserves older terms for some customers who accepted before December 2025. Consequently this note does not claim to identify the particular key's accepted contract.

The older [Kazakhstan API rules](https://law.2gis.kz/api-rules/ru) contain a Directory API clause 3.3 restricting simultaneous use with third-party digital maps. That document should not be silently substituted for the newer Platform offer. Its scope and applicability must be distinguished from the current paid or trial arrangement. There is no basis in the current offer alone for claiming that a transient custom source profile must be replaced by a provider-native iframe.

The [Platform Manager agreement](https://law.2gis.ru/platform-manager) covers the account/key-creation service, including limited test keys. It does not independently resolve all Places API usage rights. The official [subscription workflow](https://docs.2gis.com/en/platform-manager/subscription/purchase) explicitly asks customers to agree to the offer and user agreement. Access working technically is evidence of capability, not proof of a particular display or storage exception.

For Qala, the resulting implementation boundary is documented calls and transient source display, provider attribution, no completed-response cache, no persistent API-derived POI catalogue, images, reviews or identifier crosswalk. The MapLibre renderer remains the selected map. This is an engineering scope based on the provisions found, not a guarantee about undisclosed account-specific conditions.

## Query and field semantics

The official [georestriction guide](https://docs.2gis.com/en/api/search/places/examples/georestriction) distinguishes `location=lon,lat` proximity search from the stricter `point=lon,lat&radius=200` radial filter. The runner uses the latter and still validates actual returned entity coordinates within 200 metres. It never substitutes a viewport or centroid for an unavailable entity point.

The [Places API reference](https://docs.2gis.com/en/api/search/places/reference/3.0/items) exposes name components in `name_ex`, including the primary name, and separate general/organization review statistics. Field availability depends on permissions. The runner counts field presence only; it neither combines native count families nor publishes numerical ratings/review totals as a scraped dataset. A photos flag is not a photograph. It does not request or invent review prose or image URLs.

The [API overview](https://docs.2gis.com/en/api/search/places/overview) explains that successful service requests use `meta.code=200`; HTTP 200 alone is insufficient. Queries target active objects, so absence alone is not an authoritative operator closure statement.

## Reproducible diagnostics runner

`scripts/crawl_twogis_api.py` accepts at most twenty explicit named local POI IDs per run. Queries and coordinates derive exclusively from `data/pois.json`; arbitrary caller text cannot turn it into a citywide collector. It calls only `https://catalog.api.2gis.com/3.0/items`, refuses redirects, configures zero transport retries and a bounded timeout, caps decompressed responses at 2 MiB, and paces requests by at least three seconds through the shared ledger.

Identity evaluation accepts an exact existing alias or the provider's explicit primary-name component, actual coordinates within 200 metres, and a unique provider/local branch. Missing coordinates, multiple branches or a truncated response cannot become verified identity. Only decision/coverage counts are retained. Full responses, provider identifiers/names/coordinates, contact details, ratings, photos, review prose and crosswalks remain absent from output and control state.

The private ledger's `2gis_catalog_api` identity is distinct from the blocked public `2gis` site. API errors stop persistently without retrying the public site or another endpoint. Successful unchanged local seed fingerprints are skipped on later diagnostic runs, preserving original acquisition times. This resumes a test campaign; it does not cache Products for subsequent display. JSON diagnostics and partial progress are written atomically. Error records contain fixed codes and a keyless endpoint, never exception URLs, provider error prose or credentials.

Example after placing the owned key in the ignored `.env` file:

```bash
.venv/bin/python scripts/crawl_twogis_api.py \
  --seeds /path/to/explicit-local-seeds.json \
  --out /path/to/diagnostics.json --limit 2
.venv/bin/python -m pytest backend/tests/test_twogis_api_audit.py -q
```

The seed file is a list of local ID strings or objects with `poi_id`. It can reuse a Google pilot seed file; its free-form `query` strings are not used by this runner. No production crawl is needed to enable the separate, on-demand source profile.

## Actual owned-key integration check

After the research workstream froze its code, the root integration run used the user-provided key against the official API. The [live source verification](../../artifacts/twogis-source-verification.json) records successful Russian museum, English/Kazakh Bayterek and ordinary Starbucks lookups through the real application route. The interface was inspected at 1440×960 and 390×844; keyboard focus restoration was fixed and confirmed against the final production bundle. The licensed Commons gallery remains separate from provider gallery links.

The [two-seed diagnostic run](../../artifacts/provider-crawl/2gis-api/diagnostics.json) obtained HTTP 200 and `meta.code=200` for both named queries. The generic Bayterek result remained tentative because the source name did not exactly match its local aliases; the application uses its separately reviewed, identity-anchored by-ID lookup. The museum generic identity passed. No tentative match was promoted automatically. [Repeating the diagnostic run](../../artifacts/provider-crawl/2gis-api/resume-proof.json) made zero new requests and preserved the original record hashes and acquisition dates. Only diagnostics are retained; this is not a two-place export of the returned Products.
