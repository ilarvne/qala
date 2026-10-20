# Citywide Astana POI evidence upgrade

Historical report for the 19 October OSM collection. The current published corpus and the implemented Overture/Wikidata expansion are documented in [the 20 October collection report](poi-expansion-2026-10-20.md). Counts and future-source assessments below describe the earlier snapshot.

Collected on 19 October 2026. The source brief was reread from the new attachment, including the requirement that participants collect the dataset automatically, the five example scenarios, source-versus-generated distinctions, uncertain opening hours, group planning, multilingual advice and accessibility.

The previous dataset covered a central rectangle and contained 486 records. The new collection queries the complete [OpenStreetMap Astana administrative relation 3087155](https://www.openstreetmap.org/relation/3087155), including outer districts and the airport. Live Nominatim and Overpass responses independently confirmed its identity, administrative level and bounds. Every original POI ID remains present.

This is a complete extraction of the selected mapped feature types in the retained response, **not a claim that every physical business, accessible entrance, photograph or customer opinion in Astana has been documented**. Open map coverage and community reviews have real gaps.

## Shipped coverage

| Evidence | Count |
|---|---:|
| Raw mapped elements in the citywide response | 10,559 |
| Normalized POIs | 6,222 |
| Named POIs | 4,017 |
| Unnamed useful public features, labeled from their mapped type | 2,205 |
| Opening-hours strings | 1,893 |
| Operator schedules independently checked | 2 |
| Websites / phone numbers / addresses | 1,323 / 1,512 / 613 |
| Source-written descriptions, including exact-entity Wikidata descriptions | 93 |
| Wheelchair yes / limited / no / unknown | 167 / 26 / 103 / 5,926 |
| Exact Wikidata / Wikipedia links | 76 / 58 |
| Attributed photographs / photographed POIs | 34 / 22 |
| Unique optimized cached photograph files | 31 |
| Genuine available place ratings | 1 |
| Customer opinion texts | 0 |
| Explicit mapped power-supply evidence | 0 |

The categories are 328 cafes, 305 dining venues, 109 nightlife venues, 258 parks/natural destinations, 336 playgrounds, 821 sports features, 226 culture features, 8 museums, 1 viewpoint, 2,002 shops, 129 accommodation records, 35 transport features and 1,664 useful service/public-infrastructure features. Categories preserve exact cafe semantics: a restaurant or pub cannot enter a coffee-only filter. Private/no-access features are marked `recommendable: false`; transport, accommodation and utility records remain available as inventory without becoming default sightseeing recommendations.

The raw response retains excluded mapped features. Normalization rejected 1,035 out-of-scope feature types, 3,292 unnamed non-public/non-useful records and 10 duplicates. No invalid coordinates were retained. Named co-located duplicates retain their alternate OSM IDs; distinct unnamed public features are not collapsed merely because they share a type or nearby coordinates.

## Brief-to-data mapping

| Brief requirement | Evidence and behavior |
|---|---|
| Place name and approximate coordinates | OSM element identity/version/timestamp, multilingual mapped names, coordinate-origin note; way/relation centers are not presented as surveyed entrances. |
| Short description | Source description where available; otherwise a clearly derived mapped-type description. Exact-entity Wikidata descriptions retain CC0 attribution. |
| Category/tags | Whole-value OSM classification plus explicitly derived interest tags. No review-based quietness or socket availability is invented. |
| Opening hours and basic contacts | Raw mapped hours, phone, website, email and address; two independently checked operator schedules retain separate URLs and collection times. Unknown remains unknown. |
| Rating/popularity if available | One real signed Mangrove rating with original scale, source and count; all other ratings remain null. OSM hotel `stars` and Overture existence confidence are not customer ratings. |
| Current context and walking | Geographic coordinates, exact feature category and hours support retrieval filters; route time is handled separately by the agent/router. |
| Children, group and accessibility | Playground/park/museum inventory plus source wheelchair status, entrance, step count, surface, lighting, tactile paving and hearing-loop fields where mapped. No guarantee of accessible routing is inferred. |
| Honest generated suggestions | Data records distinguish source descriptions from derived category text; visit ideas remain agent output rather than fabricated source facts. |
| Automatic collection | One command runs OSM → operator facts → licensed media → signed public reviews → CSV/GeoJSON/coverage exports. Offline replay reparses retained evidence and verifies it without a network request. |

## Automated collection and replay

```bash
uv run python scripts/refresh_dataset.py --live
uv run python scripts/refresh_dataset.py --replay
```

`--live` stages the new dataset and publishes it after collection stages succeed. The public Overpass collector rejects partial/error responses and preserves the existing dataset if collection fails. It tries documented public mirrors, exact category matching and a city boundary area filter. A retained Overpass response may be supplied with `--live --raw data/raw/astana-overpass-citywide.json`; enrichment still uses live sources in that mode.

`--replay` makes no network requests and does not modify the published corpus. It reprocesses raw OSM records, reparses retained operator HTML or the packaged short source excerpts using the same fact checks, validates photograph metadata/license/credit against retained Commons API responses, and verifies the original review JWT signatures. Its coverage must equal the published coverage. The actual offline replay passed for all 6,222 POIs, 34 photos and one rating.

The individual collectors remain usable:

```bash
uv run python scripts/collect_pois.py
uv run python scripts/enrich_poi_media.py --cache
uv run python scripts/enrich_poi_reviews.py
uv run python scripts/export_poi_dataset.py
```

Use a descriptive operator contact in `QALA_DATA_USER_AGENT` when running repeated public API refreshes. Wikimedia calls are serial, use small image-metadata batches, honor bounded `Retry-After`/backoff and retain failed-source reporting. The pipeline does not bypass API rate limits or scrape provider endpoints.

## Photographs

Photos are joined through exact OSM `wikidata`/`wikimedia_commons` links, Wikidata P18 statements or directly linked Commons categories. Generic nearby imagery and similar-name search results are not assigned to places. Explicit entity images take precedence over category order.

Each photo contains its source file page, plaintext author/credit, license name and URL, observation time and original/thumbnail links. Optimized copies are served from `public/photos`; the attribution manifest is `data/photo-attributions.json`. No generated image is labeled as a real place photograph.

The collected images were visually inspected. Currency reproductions, visitor portraits, airport route diagrams, outdated construction photographs and unrelated skyline covers were removed. The National Museum uses a checked atrium photograph and an exhibit photograph. The small source-file curation list in `data/photo-curation.json` is reapplied by future automatic refreshes; it does not invent architectural models or replace source facts.

Commons supplies individual photographer licenses, which can differ by file. Source pages can also describe restrictions relating to depicted works or other rights; a photo's declared license is not a blanket assertion about every underlying right. Delisted or changed source files should be checked during a new publication. The original API metadata is retained for inspection.

## Real open ratings and reviews

[Mangrove's public API](https://docs.mangrove.reviews/) and [Open Reviews terms](https://mangrove.reviews/terms) permit reuse under each review's declared license, defaulting to CC-BY-4.0; CC-BY-SA-4.0 is also supported. Both the full Astana bounding-box query and a 40 km geographic-radius query returned the same single record.

The record identifies the **Overhead** cafe by exact OSM metadata `node/14201388401/1`. Its source rating is **70/100**, rendered as **3.5/5**, with **one rating and no opinion text**. The conversion and original scale are retained in `rating_source` and the review record. The rest of the corpus has null ratings. The app must not display imaginary customer quotations or infer a large sample from a single score.

The importer checks the original ES256 JWT against its public key, verifies the returned payload and accepts only exact OSM identities with consistent geography and an allowed license. The API canonicalizes query-parameter order in geo subjects; the verifier compares equivalent subject URIs and verifies the untouched original JWT bytes. Modified ratings and signatures fail the tests. A valid signature proves key authorship/integrity, not a verified visit or the truth of an opinion. The public reviewer key is represented by a fingerprint for attribution; no private key or personal profile is collected.

Review provenance is in `data/review-attributions.json`; the original public signed response is in `data/raw/mangrove-astana-bbox.json`. The signature-specific API source remains directly accessible.

## Provider evaluation

The research used Exa across eight successful search calls requesting 43 results, then inspected the relevant primary documentation and live APIs. The source comparison matters because adding a fabricated rating or an incorrectly licensed image would lower the quality of the assistant.

- [Overpass area filtering](https://dev.overpass-api.de/overpass-doc/en/full_data/area.html) supports a true administrative-city extraction instead of a convenient downtown rectangle. [OSM attribution and ODbL terms](https://www.openstreetmap.org/copyright) accompany the database.
- [MediaWiki imageinfo](https://www.mediawiki.org/wiki/API:Imageinfo/en) and [CommonsMetadata](https://www.mediawiki.org/wiki/Extension:CommonsMetadata/en) provide per-file author/license metadata. [Wikimedia's 2026 rate-limit guidance](https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits) requires client identification, modest concurrency and backoff.
- [Mangrove's standard](https://mangrove.reviews/standard), [schema guide](https://mangrove.reviews/schema-guide) and [open dataset explanation](https://open-reviews.net/technology/) provide interoperable place IDs, signed ratings and reusable review licenses. Actual Astana coverage is currently very sparse.
- [Google Places policies](https://developers.google.com/maps/documentation/places/web-service/policies) restrict bulk caching and require Google Maps when Places results are displayed on a map. No authorized Google Places credential was configured. Its photos/reviews were not copied into a permanent MapLibre dataset. This avoids a provider-specific integration that would contradict the selected embedded map.
- [Overture's current Places schema](https://docs.overturemaps.org/schema/reference/places/place/) can expand business coverage, but does not supply a general customer-review/photo corpus. Its [official coverage/quality guidance](https://docs.overturemaps.org/guides/places/) warns about duplicates, junk and missing properties; its confidence field measures existence, not popularity. It is a separate future source, not silently relabeled as a customer rating or mixed into the verified OSM snapshot.

## Artifacts and verification

- `data/pois.json`: complete normalized runtime inventory, source facts and derived-field distinctions.
- `data/pois.csv` / `data/pois.geojson`: reusable tabular/spatial exports.
- `data/dataset-manifest.json`: category/field coverage, source metadata, file sizes/hashes and six passed evidence checks.
- `data/raw/astana-overpass-citywide.json` / `data/raw/astana-boundary.json`: citywide collection and boundary evidence.
- `data/raw/media/`: original public entity and photo-license metadata.
- `data/photo-attributions.json` / `data/review-attributions.json`: individual content provenance and license records.
- `backend/tests/test_poi_collection.py`: seven focused tests for whole-value categories, dedup, private access, explicit outdoor evidence, licensed photo parsing, real review signature tampering and rating-only behavior.

The published `data/pois.json` SHA-256 is `e5aa17c3ba1a4437b0f3ea7bf589360222b8198797c53865a5f130867cfd20f3`. All six export-manifest evidence checks passed. Remaining data gaps are measured rather than filled with invented values: no customer opinion text, only one available rating, photos for 22 of 6,222 records, 5,926 unknown wheelchair statuses and no explicit power-supply tags.
