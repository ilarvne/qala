# Astana 3D SDK: coverage, integration and access

Research date: 19 October 2026. This extends [the initial provider check](astana-provider-coverage.md) with new direct SDK observations, regional pricing and operational requirements. No application source was changed. A project-owned map key was not available in this workstream, so the application's successful authenticated 3D path remains unverified; the observations below come from provider-hosted SDK previews.

## Finding

2GIS MapGL is the strongest tested ready-made **detailed landmark renderer** for Qala, but it is not a complete accurate 3D model of Astana. Five of seven tested landmarks had distinctive architectural geometry; the Circus remained a cylinder and the Kazakh Eli column was not visible in the tested views. Yandex JS API v3 also supplies recognizable geometry for Nur Alem and Bayterek, and displayed the Kazakh Eli column absent from the tested 2GIS view. Its tested SDK rendering was pale and much less detailed than the colored consumer presentation.

A claim of a complete or survey-accurate city model would need a different source dataset and independent validation. An SDK supporting mesh rendering does not establish that it supplies such a dataset.

## Actionable comparison

| Option | Geometry directly verified | Qala route/pin/camera integration | Access and commercial consequence | Recommendation |
| --- | --- | --- | --- | --- |
| 2GIS MapGL JS 1.78.1 | Nur Alem, Bayterek, Khan Shatyr, Opera, Triumphal Arch; gaps below | Native HTML markers, line geometry, events, camera/padding and styles | Own Map Tiles API key; one-month demo or paid service; Kazakhstan calculator currently shows **KZT 49,440/month for 100,000 tile requests** | Best tested visual result for the original two failures; audit required landmarks before adopting a city-wide accuracy claim |
| Yandex JS API v3 | Nur Alem curved mesh, Bayterek distinctive upper structure, Khan Shatyr tent geometry, Kazakh Eli column | Native DOM markers, geometry and event APIs; requires own key | Free use exists for qualifying public projects, subject to regional terms, attribution and possible advertisements; referer restriction required | Credible lower-cost geometry alternative; test actual project key and visual requirements before choosing it |
| Yandex public widget | Consumer Nur Alem sphere previously verified by root agent | Share-generated place/route embedding; no documented arbitrary Valhalla polyline and marker-event bridge found | Legitimate free viewer, no project API key required | Optional external viewer; does not replace Qala's native route map |
| 2GIS On-Premise | Architecture supports immersive tile/model data; this project's licensed local dataset not obtained | Same native MapGL integration with locally hosted services | Commercial licensed server deployment, storage and operations | Viable for controlled/offline delivery if the purchased Astana data includes the required models; disproportionate for a hackathon preview |
| Urbi MapGL | Same MapGL product family and substantially matching official documentation | Same general integration model | Own service agreement/key | Not independently verified as a different source of missing Astana geometry |

## Landmark evidence

The main 2GIS observations use the [official public Map Tiles API playground](https://platform.2gis.ru/en/playground/mapgl/), its blank/default style, close zoom, and a 45° pitch. Coordinates below are `[longitude, latitude]`. All models were assessed after loading settled, with additional checks for negative results. These seven observations are a test set, not a statistical estimate of city coverage.

| Landmark | Coordinates | Observed 2GIS result | Evidence |
| --- | --- | --- | --- |
| Nur Alem / Alem AI | `71.41607, 51.08921` | Curved sphere, panel mesh, top aperture, pedestal and modeled neighboring buildings | [Default preview](../../artifacts/screenshots/2gis-preview-nuralem.png), [normal preset](../../artifacts/screenshots/2gis-normal-nuralem.png) |
| Bayterek | `71.4304546, 51.1282882` | Gold sphere, open metal lattice and circular base | [Default preview](../../artifacts/screenshots/2gis-preview-bayterek.png), [normal preset](../../artifacts/screenshots/2gis-normal-bayterek.png) |
| Khan Shatyr | `71.4038726, 51.1325089` | Sloping tent, mast and detailed canopy ribs | [Preview](../../artifacts/screenshots/2gis-deep-khan-shatyr.png) |
| Astana Opera | `71.410753, 51.1354512` | Roof forms, facade and portico columns | [Preview](../../artifacts/screenshots/2gis-deep-opera.png) |
| Mäñgilik El Triumphal Arch | `71.4300836, 51.1043034` | Recognizable arch openings and facade geometry | [Preview](../../artifacts/screenshots/2gis-deep-arch.png) |
| City Circus | `71.4189112, 51.1450693` | Circular vertical extrusion; its distinctive flying-saucer roof was not supplied in the settled view | [Settled preview](../../artifacts/screenshots/2gis-deep-circus.png) |
| Kazakh Eli | `71.4698815, 51.1221098` | The column was not visible at zoom 18.5 or in a wider settled zoom-16.5 view; surrounding modeled buildings were visible | [Wide preview](../../artifacts/screenshots/2gis-deep-kazakh-eli.png) |

Kazakh Eli's location was cross-checked against the [2GIS object page](https://2gis.kz/astana/geo/9570844992864275), which gives `51.12213, 71.469878`. The absence reported above concerns these actual tested SDK views, not a promise that the provider never has or will have a model. The wide view also showed a detailed Hazret Sultan Mosque model nearby, though that was not a separate coordinate/preset test.

### Presets: direct runtime verification

The [official graphics-preset documentation](https://docs.2gis.com/en/mapgl/map/configuration/graphics-presets) includes an interactive map with a preset selector. Its v1.78.1 map was moved to Nur Alem and Bayterek using the existing provider-hosted instance. Both detailed models remained visible with **normal** selected.

`getGraphicsPreset()` returned:

| Preset | `modelsOff` | `shadowsOff` | Other relevant observation |
| --- | --- | --- | --- |
| normal | false | true | Detailed sphere/lattice retained |
| immersive | false | false | Adds shadows; higher graphics cost |
| light | true | true | Removes mesh models, including landmarks; unsuitable as an equivalent accurate 3D mode |

This agrees with [release v1.76.1](https://docs.2gis.com/en/mapgl/releases), which changed the default preset behavior on 14 August 2026. Presets are style-configurable: a custom style can define different behavior. The main playground does not initialize preset mode, so merely patching its `graphicsPreset` variable would not have been a valid preset test; the documentation's actual preset-enabled instance was used instead.

## Production integration

### Own key, regions and billing

- [Creating keys](https://docs.2gis.com/en/platform-manager/subscription/keys): the cloud demo is available once for one month. It can later be converted to production after a subscription purchase. No account or key was created during this research.
- [Current billing documentation](https://docs.2gis.com/en/platform-manager/subscription/pricing): demo Map Tiles access allows **500,000 requests**. Production Map Tiles usage has a **3,000 requests/minute** service cap and purchased monthly limits. Limits are shared across keys in a subscription; key-specific lower limits and notifications are supported.
- A billing unit is a successful 256×256 vector-tile request, not a user, map session, route, or landmark. Panning, zooming, viewport size and additional requests affect actual use. The docs' 800×600 example needs 12 visible tiles, or about 30 with a one-tile border; this is not an exact per-session budget.
- The [public Kazakhstan pricing calculator](https://platform.2gis.com/en/tariffs), with country set to Kazakhstan, one-month billing, and only Map Tiles API selected, displayed **100,000 requests/month for KZT 49,440**. [Captured quote](../../artifacts/screenshots/2gis-kz-maptiles-quote.png). This was a read-only quote, not a purchase or submitted request. The documented Russian RUB schedule should not be presented as a Kazakhstan invoice.
- The official Kazakhstan marketing site also contains an older customer story describing fixed annual map licensing. That does not override the live calculator's tile-based offer; any bespoke annual contract needs its own quote.

[Key management](https://docs.2gis.com/en/platform-manager/subscription/managing-keys) supports restrictions using `Origin`, `Referer`, `User-Agent`, IP/subnets and mobile App ID. Restrict a browser key to the actual deployment origins and test development access separately. The examined docs do not specify a universal localhost/wildcard syntax; that configuration remains to be verified with the project's own key. The mobile App ID setting is not a substitute for web origin restrictions.

### Routes, pins and camera: actual primitive checks

2GIS supplies [native markers and geometry](https://docs.2gis.com/en/mapgl/overview/features), so Valhalla route geometry can be rendered without asking 2GIS to calculate the route. Mapping and provider routing are separate capabilities; using a route line does not itself require a 2GIS route calculation. The applicable commercial agreement should cover the chosen usage.

The following were tested on the official existing MapGL instance without moving any provider key to Qala:

- `HtmlMarker` with a DOM wrapper, button carrying `data-place-id`, `[17.5, 17.5]` anchor and `interactive: true`: `getContent().querySelector('[data-place-id]')` found the button; its click listener fired; after rendering, its center matched `map.project()` within 0.5 px. `destroy()` removed the DOM.
- [fitBounds](https://docs.2gis.com/en/mapgl/map/configuration/fitbounds) already includes map padding. In a 472×553 viewport, map bottom padding of 230 px plus ordinary `fitBounds` produced the same projected bounds as zero map padding plus a 230 px fit padding, within 0.0001 px. All corners fit at y≈59–264, above the inset boundary at y=323. Adding the inset a second time is unnecessary.
- `fitBounds(..., { animation: { animate: false } })` updates center/zoom getters synchronously and resets pitch to zero. Saving camera state, calculating the fit, and restoring camera state in the same synchronous call works. Projection matrices settle on the following render frame, so `project()` should not be treated as immediately updated in that calculation call.
- Retargeting `setZoom` with `{ animate: false }` stopped an actively running long zoom animation and held the new value.

### Flat 2D is a geometry change

The earlier live test hid layer types `model`, `polygonExtrusion`, `lineExtrusion`, and `polygon3d`, then set pitch to zero. All vertical geometry and trees disappeared; small 2D POI icons remained. Restoring those types restored 3D. Presets do not replace this: [3D-model documentation](https://docs.2gis.com/en/mapgl/map-style/immersive/models) says preset model controls do not hide ordinary raised building polygons.

Apply layer changes after `styleload` and reapply them after style replacement. [Runtime style documentation](https://docs.2gis.com/en/mapgl/map-style/modify) explains that loading a style overwrites earlier layer edits. Keep landmark models supplied by the provider; do not compensate for missing source geometry with hand-made landmark patches.

### Loading and failure

Bayterek first appeared as a plain cylinder in the initial research visit, then changed to the detailed mesh after its assets loaded. Therefore an early screenshot or a camera-idle callback is insufficient to classify coverage.

The [event reference](https://docs.2gis.com/en/mapgl/reference/interface#map-event-table) says `idle` excludes asset loading. The public v1.78.1 types inspected here expose `styleload`, `styleloaderror`, and the `error` event with `invalidtilekey`, `styleloaderror`, and `webglcontextlost`. No documented general completion event for every built-in landmark model was found. Do not substitute custom glTF-plugin load events: those apply to separately added plugin models. If an acceptance requirement forbids even temporary simple geometry, obtain a supported base-model readiness contract from 2GIS rather than relying on private renderer internals.

Validate missing/invalid/expired/restricted keys, exhausted limits, network failure and context loss. Preserve a usable flat map, with the failure detail inside the relevant map/provider interaction. Do not label an unresolved or partially loaded view an accurate city model.

### Performance and attribution

[Browser support](https://docs.2gis.com/en/mapgl/overview/browser-support) covers current desktop Chromium, Firefox and Safari plus documented mobile versions, but explicitly says browser version alone does not guarantee driver/hardware compatibility. Use `isSupported()` and handle failure.

The research browser identified its renderer as SwiftShader software rendering. Both ordinary `isSupported()` and the performance-caveat check returned true there. Consequently these screenshots establish geometry, not acceptable mobile FPS or cold-load performance. Benchmark the project's own production page on representative Android/iOS hardware and a constrained network. Start with normal rather than light if retaining actual models is required; disable unnecessary expensive effects through a controlled style, and measure their benefit.

[Controls documentation](https://docs.2gis.com/en/mapgl/map/configuration/controls) requires the map copyright to remain visible and unobscured. Move it with `copyright`/`setControlsLayoutPadding` so Qala's route panel cannot cover it. This is required map attribution, not optional decorative UI copy.

[Release policy](https://docs.2gis.com/en/mapgl/releases) recommends the maintained `/api/js/v1` endpoint. A fixed version such as 1.78.1 needs planned upgrades because fixed releases have a limited support period. Locking npm types alone does not pin an independently loaded hosted renderer.

## Offline / on-premise boundary

A cached consumer map or a mobile SDK's offline-download feature is not a licensed offline web deployment.

2GIS offers a supported on-premise path. Its [map installation instructions](https://docs.2gis.com/en/on-premise-api-platform/api-platform/install/maps) include base `web` tiles and the `immersive` subtype for 3D models, MapGL JS, a tile service, style/model assets and supporting storage/services. [License architecture](https://docs.2gis.com/en/on-premise-api-platform/architecture/license) supports operation without continued Internet access after the license is generated and stored locally. That remains a time-limited commercial license, not an unrestricted data download.

The deployment requires infrastructure such as Kubernetes, artifact/model storage, the license/key services and Cassandra-backed tiles. Confirm that the purchased geographic package contains the required Astana immersive data, that its update schedule is acceptable, and that the chosen delivery rights cover the actual application. The cloud preview alone does not prove those commercial deliverables. [Map Tiles API documentation](https://docs.2gis.com/en/maps/others/maptiles/overview) says direct cloud-vector-tile integration without the 2GIS SDK is not supported.

## Yandex: SDK geometry is now verified

The [official JS API customization example](https://yandex.com/maps-api/docs/js-api/examples/cases/customization.html) contains a real API v3 map, not a consumer widget. Its existing hosted map was switched to vector mode, moved to the test coordinates, tilted, and its example-specific gray customization reset to the default. No key was exported into another application.

Observed there:

- Nur Alem: curved sphere mesh and top geometry rather than a footprint cylinder.
- Bayterek: recognizable upper structure and modeled base, in a pale building material.
- Khan Shatyr: tent geometry, again pale.
- Kazakh Eli: tall column and base present at the same location where the 2GIS test did not show the column.

The API example did not establish parity with consumer maps' colored, textured landmark assets. [Yandex's own model specification](https://yandex.ru/project/maps/3d/tech) distinguishes monochrome geometric models from selected professionally colored landmarks. It also describes simplified, sometimes enlarged details, so neither appearance should be called survey-grade.

Retained SDK captures: [Nur Alem](../../artifacts/screenshots/yandex-sdk-nuralem-default.png), [Bayterek](../../artifacts/screenshots/yandex-sdk-bayterek-deep.png), [Khan Shatyr](../../artifacts/screenshots/yandex-sdk-khan-shatyr-deep.png), and [Kazakh Eli](../../artifacts/screenshots/yandex-sdk-kazakh-eli-deep.png).

The [v3 quick start](https://yandex.com/maps-api/docs/js-api/quickstart.html) requires the project's own API key and configured HTTP Referer restrictions; activation can take up to 15 minutes. Its regular DOM-marker, line-geometry and event system can support a native Qala map. Custom Deck.gl/GLTF layers are a separate experimental option requiring support enablement; they are not needed merely to display the map's existing landmark geometry.

### Free license and regional pricing require care

[Yandex's official free-use conditions](https://yandex.ru/dev/commercial/doc/ru/?from=mapsapi) permit a qualifying freely accessible public project and require visible attribution and the Open in Maps control. Restricted/paid access, redistributing data, and prohibited uses need different terms. Ads may be supplied. A free API license still requires an owned key.

The regional documents differ. The [Kazakhstan terms](https://yandex.kz/legal/maps_api/ru/) currently describe 25,000 combined geocoding/routing/panorama requests per day, including no more than 1,000 HTTP geocodes; they do **not** describe 25,000 map loads. The newer [Russian terms](https://yandex.ru/legal/maps_api/ru/), dated 1 September 2026, instead specify 100 panorama calls/day in the JS API section. Confirm the agreement attached to the actual Kazakhstan account/key. The [Kazakhstan product tariff](https://yandex.kz/maps-api/products/js-api) includes panorama-tier prices; its KZT 1,064,000 annual figure should not be presented as an unavoidable fee for basic map display.

### Why the free widget is not a seamless replacement

[Yandex's sharing documentation](https://yandex.com/support/maps/en/concept/get-map-reference) authorizes embedding a generated widget for a location or route. [Its no-programming tools page](https://yandex.com/dev/maps/mapstools/) explains that a route widget redraws its own route at viewing time. It does not promise to preserve an externally calculated Valhalla path. No documented widget interface was found for arbitrary route geometry, custom DOM pin events, or synchronized selected-place state; cross-origin iframe content cannot be directly controlled by Qala. A shared route viewer is useful, but is a different interaction from the native SDK integration.

## Remaining decisions

1. Decide whether the requirement is selected recognizable landmarks, fuller city geometry, or a licensed photogrammetric/survey model. The tested SDKs satisfy different parts of that range.
2. For the near-term native map, compare 2GIS normal against Yandex vector using the same fixed required-landmark list and the project's own keys; include the Circus and Kazakh Eli counterexamples.
3. Confirm the applicable key/license and cost before production deployment. Keep demo or documentation keys on their own provider-hosted pages.
4. Validate geometry, truly flat 2D, route/pin interaction, asset loading, attribution and hardware performance separately. None can be inferred solely from the others.

Method: 18 new Exa searches, 90 result slots including overlapping/irrelevant results, followed by primary-page reads and direct public SDK tests. This is separate from the initial report's 70 result slots and is not a count of 90 unique validated sources.
