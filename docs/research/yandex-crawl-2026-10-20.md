# Yandex: actual public-card crawl and integration assessment

Checked on 20 October 2026. This investigation used Exa for eight discovery queries requesting **47 results**, deduplicated into 45 URLs. Those are discovery counts, not 47 successfully crawled organizations. [Discovery record](../../artifacts/provider-crawl/yandex/discovery.json).

## Observed results

Two ordinary, unauthenticated HTTP requests returned complete public organization cards before an ordinary browser request received HTTP 429. Collection stopped at that point. No subsequent organization, alternate domain, proxy, widget, CAPTCHA or authenticated endpoint was requested as a workaround. [HTTP evidence](../../artifacts/provider-crawl/yandex/http-attempts.json), [browser access evidence](../../artifacts/provider-crawl/yandex/browser-access.json).

| Public organization | Exact organization ID | Coordinates, latitude / longitude | Rating | Ratings | Written reviews |
| --- | --- | --- | --- | --- | --- |
| [Bayterek](https://yandex.com/maps/org/bayterek/225535630402/) | 225535630402 | 51.128197 / 71.430444 | 5.0 / 5 | 12,913 | 3,339 |
| [National Museum](https://yandex.com/maps/org/national_museum_of_the_republic_of_kazakhstan/25328584978/) | 25328584978 | 51.118268 / 71.468742 | 5.0 / 5 | 4,014 | 1,313 |

These values were read from the exact organization's public `application/json.state-view` metadata and agree with the public AggregateRating markup. They are provider observations at the recorded collection time, rather than verified visitor testimony or guaranteed future values. Index snippets had older totals, which is why they were not substituted for fresh card observations.

The two cards also delivered 20 photograph source references. Image bytes were not downloaded, and these references are not licensed assets. Individual review bodies, author names and avatars were not exported. [Sanitized observations](../../artifacts/provider-crawl/yandex/observations.json).

The ordinary browser's main document returned **429** with body `limited`. Its [screenshot](../../artifacts/provider-crawl/yandex/browser-limited.png) and status are preserved. An allowed robots path is not evidence that a rate limit can be bypassed. The recorded `yandex.com` and `yandex.kz` robots files allowed the organization path for the declared research user agent; the later denial still ended this collection.

## Implementation

[`scripts/providers/yandex.py`](../../scripts/providers/yandex.py) exposes `parse_html(html, url, *, observed_at=None) -> list[dict]` for the shared provider crawler. It executes no scripts and makes no requests. It requires the numeric ID in the public URL, business object and public URI to match. It ignores viewport/city-center coordinates, related organizations, user reviews and session fields. Numeric bounds, URL host checks, response-size bounds and source-link sanitization are enforced. Missing fields remain unknown. Eight focused tests cover identity mismatches, viewport confusion, invalid numbers, session leakage, source URL validation, malformed content and original/unknown acquisition times. Parsing cached HTML never establishes a new observation date. The original six-test acquisition proof remains historical.

Both observations are manually linked to the existing OSM landmark entities. The National Museum transport stop and an unrelated restaurant named Байтерек are not matched. All provider observations retain `import_policy: evaluation_only`; the existing public corpus and MapLibre renderer are unchanged.

Raw card responses include provider session metadata and third-party review prose. They are kept under the ignored `.local/provider-crawl/yandex/raw/`, with restricted file permissions, and are excluded from the submission. Public evidence records body hashes, request times and minimal allowlisted metadata instead.

## Official integration options

The supported [Places API response](https://yandex.com/maps-api/docs/geosearch-api/response.html) provides organization identity, coordinates, address, contact details, categories, hours and accessibility features. Its supported schema does **not** promise ratings, review bodies or photographs. Search returns ranked matches, rather than an exhaustive city directory. Buying a basic Places API subscription therefore does not by itself deliver the requested review/photo dataset.

Current [Kazakhstan Russian-language Places terms](https://yandex.kz/dev/tariffs/doc/ru/geosearch/terms/) require the Yandex map background for displayed API results and permit a limited performance cache under the standard contract. The [Kazakhstan tariff](https://yandex.kz/dev/tariffs/doc/kk/geosearch/prices/) separately advertises an extended retention licence. That tariff does not establish that every map, ranking, photograph or review reuse restriction is removed; the actual granted contract must determine scope. The existing MapLibre application should not silently import these API results as a redistributable open dataset.

The current official [sharing instructions](https://yandex.ru/support/maps/ru/concept/get-map-reference) separately allow a provider-owned **review widget** on a website or blog, obtained from an organization card's Share control. The instructions specify a width of 300–760 px and recommend at least 500 px height. They do not state that organization ownership must be verified. A lazy widget within a place's source/reviews interaction could preserve provider attribution and keep reviews provider-hosted while Qala retains its current map. This is a practical candidate, **not a live-verified integration**: no widget request was made after the rate-limit response, and no review data was extracted from an iframe.

## Next operational step

Keep an organization-ID crosswalk, an explicit collection budget, per-origin pacing, robots checks, cache freshness and a persistent stop ledger. A 429, access-denied response or CAPTCHA ends collection across methods; a denied origin is not rotated to another host or proxy. Further API acquisition needs an owned key and compatible granted rights. Further public-card acquisition must wait until access is available through the normal service. Source links and this evaluation remain usable for inspecting the findings in the meantime.
