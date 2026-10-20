# Astana pedestrian routing

Verified 19 October 2026. The recommendation planner still supplies a rough walking budget. When the user starts navigation, `POST /api/navigation/route` requests a separate pedestrian route from Valhalla. Only a successful, validated provider response becomes a navigation line or turn instruction. Provider failure never becomes a straight line or invented directions.

## Provider choice and sources

[Valhalla's current routing API](https://valhalla.github.io/valhalla/api/route/api-reference/) documents pedestrian costing, ordered break locations, encoded polyline geometry with six decimal places, per-leg summaries and maneuver instructions. English and Russian are supported narrative languages; Kazakh is absent from the supported-language list. Qala requests English for Kazakh and returns `language_requested: "kk"`, `language_used: "en"`, `language_fallback: true` plus an explicit warning. It does not claim translated Kazakh turns.

[Valhalla's public demo guidance](https://valhalla.github.io/valhalla/) identifies the FOSSGIS-hosted global graph at `https://valhalla1.openstreetmap.de`, asks clients to follow fair use, identify themselves with `X-Client-Id`, and notify the project before publishing an end-user application. The adapter sends that header, serializes provider calls, limits each client to twelve navigation requests per minute and reuses identical routes for five minutes. This is a local demonstration using the public service; production should use an operator-controlled instance or agreed hosting. No project notification or external publication was performed.

The routing line uses OpenStreetMap data. Responses carry the provider name and [OpenStreetMap attribution link](https://www.openstreetmap.org/copyright), which the map should display.

## API contract

```json
{
  "coordinates": [[71.4073, 51.0897], [71.4029, 51.0893]],
  "language": "en"
}
```

Coordinates use longitude, latitude order. Two to four ordered stops are accepted within longitude 71.15–71.75 and latitude 50.95–51.35. Booleans, string numbers, non-finite numbers, duplicate consecutive stops, extra fields and arbitrary provider URLs are rejected before contacting the router. The only languages are `en`, `ru` and `kk`.

Successful responses contain:

- `geometry`: a GeoJSON `LineString`, preserving the decoded street-path vertices.
- `distance_m`, `duration_seconds`: provider totals, converted from metric summaries.
- `legs`: distance, duration and `steps` containing provider `instruction`, distance, duration, `[longitude, latitude]` location and integer `maneuver_type`. `geometry_start_index` and `geometry_end_index` refer to the combined geometry.
- `bounds`: `[west, south, east, north]` for fitting the map.
- `waypoints`: requested and routed coordinates with `snap_distance_m`; a snap over 75 m generates an entrance warning, and one over 1 km is rejected.
- `provider`, `attribution`, `attribution_url`, `mode: "walking"`, `street_routed: true`, language fields, `warnings` and `limitations`.

The adapter checks metric units, successful provider status, expected leg count, bounded connected geometry, valid maneuver indices, pedestrian mode on every instruction, finite measurements, matching trip/leg totals and the requested provider narrative language. It rejects empty instructions. Responses are limited to 2 MB, 40,000 combined geometry points and 500 maneuvers per leg. HTTPX uses an 18-second timeout with a five-second connection timeout and does not follow redirects.

Input errors and an unroutable provider response return 422. Timeouts, unavailable endpoints, redirects and provider failures return 503; provider throttling also includes `Retry-After: 60`. Invalid or oversized successful provider responses return 502. Qala's own request limit returns 429. Error responses contain an explanation and no synthetic route.

`QALA_VALHALLA_URL` optionally overrides the server base URL. It requires HTTPS, except loopback HTTP for a local self-hosted server, and rejects embedded credentials, query strings and fragments. `QALA_ROUTING_CLIENT_ID` optionally supplies an operator-specific identity. Neither setting is client-controlled.

## Privacy and limits

Only stop coordinates, route options and narrative language go to the routing provider. Conversation text, session capabilities and preference memory are excluded. Qala does not write routes to the preference database or files. It keeps at most 64 routes in process memory with a five-minute cache validity window; expired entries are removed at the next route request. Successful API responses use `Cache-Control: no-store`. The external service necessarily receives the requested coordinates; its logging and retention are outside Qala's control.

POI centroids and snapped path coordinates are not verified public entrances. Navigation does not verify temporary closures, crossings, weather conditions, step-free access or venue availability. The existing recommendation budget remains an estimate until a street route has been requested. This endpoint is pedestrian routing and turn guidance; it does not provide live GPS tracking, automatic rerouting or an offline graph.

## Verification

`backend/tests/test_navigation.py` uses HTTPX `MockTransport`, not live provider traffic. It verifies the API boundary, provider payload, geometry/maneuver preservation, EN/RU/KK behavior, malformed provider data, input bounds, outages, timeout, response size, multi-leg indices, snapping disclosure, cache isolation/expiry/concurrent reuse and rate limiting. Run:

```sh
.venv/bin/python -m pytest backend/tests/test_navigation.py -q
```

Result: **49 passed**, 19 October 2026.

One separate live request completed at **2026-10-19T11:04:36Z**, using the public sample stops in the request above and `costing: "pedestrian"`. The actual provider result passed the same adapter validation:

| Observation | Actual result |
| --- | --- |
| Distance | 472.0 m |
| Duration | 331.9 seconds |
| Decoded geometry | 20 street-path vertices |
| Legs / maneuvers | 1 / 5 |
| Start / destination snap | 17.4 m / 21.9 m |
| Narrative | English |
| Provider | Valhalla |

The returned maneuvers included a walkway turn and named-street turns. This proves that the configured provider delivered a street route in Astana at the recorded time. It is not a continuous availability guarantee. The automated suite does not repeat this public-service request.
