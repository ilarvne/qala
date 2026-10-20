# Astana 3D providers: follow-up investigation

Research date: 19 October 2026. This is an implementation-focused follow-up to [the SDK landmark tests](astana-3d-sdk.md) and [the map architecture plan](astana-3d-map-plan.md). It adds six diverse Exa searches, 60 returned search-result URLs, 30 primary-page fetches, and nine recorded direct-origin checks. Search-result count is not a count of validated solutions. The [machine-readable evidence](evidence/astana-provider-followup.json) separates requested slots, returned results, unique URLs, source quality and observations.

## Decision

No newly examined provider supplies a verified, supported, credential-free native Astana 3D map that preserves Qala's walking route and selected-place interaction. That is a bounded research result, not proof that no such product can exist.

The strongest choices remain:

1. **2GIS MapGL with the project's own key** for the best already-observed rendering of Bayterek and alem.ai. Its five-of-seven landmark result and two counterexamples remain material.
2. **Yandex API v3 with the project's own key** when its qualifying free public-project license is applicable. Distinctive Bayterek, alem.ai, Khan Shatyr and Kazakh Eli geometry was already observed in the actual hosted SDK.
3. **Cesium with an authorized central-Astana mesh** for a richer independent city model. Cesium is a renderer and streaming platform; its global terrain/OSM catalog does not supply the missing detailed Astana model.

No account, key, license or entitlement was created. No vendor documentation key was copied into Qala.

## Alternatives that initially looked promising

| Provider | What exists | What prevents selecting it now |
| --- | --- | --- |
| TomTom Orbis | Real high-detail GLB landmark tiles and a native JS plugin | Private Preview entitlement and own API key required; Astana landmark coverage not established |
| HERE | Detailed textured landmarks in Navigate SDK | Current official feature matrix excludes that feature from the web JS product |
| Google / Cesium partner tiles | Photorealistic city meshes in supported countries | Kazakhstan is not advertised for 3D in the official coverage table |
| Vexcel | Real commercial 3D Tiles reality meshes | No Astana-specific coverage/sample/license identified in examined official material |
| MapTiler | Exact Astana catalog and Cesium-compatible basemaps | Advertised city catalog is OSM vectors, imagery and elevation-related layers |
| Bing / Azure | Mapping, imagery and some 3D products | No qualified Astana detailed web integration found; Bing Basic retirement rules out the old free-account path |

### TomTom: real mesh capability, unavailable entitlement and coverage proof

This is a substantive new candidate. The official [Landmarks3D reference](https://docs.tomtom.com/maps-sdk-js/api-reference/classes/plugins.Landmarks3D.html) describes GLB tile streaming, a MapLibre custom layer, suppression of overlapping footprint extrusions, and preservation across style changes. It explicitly requires Orbis 3D Landmarks entitlement and labels the service Private Preview. The [tile URL helper](https://docs.tomtom.com/maps-sdk-js/api-reference/variables/plugins.buildLandmarksTileURL.html) identifies compressed GLB and KTX2/Basis assets.

These are actual mesh capabilities, not a generic extrusion pitch. They do not establish that Bayterek or alem.ai is included. None of the examined official pages supplied an Astana footprint, landmark list or test scene.

An additional implementation trap: Exa's fetched snapshot documents an older `setDisplayMode` interface. The current origin page, independently retrieved with HTTP 200, instead documents `updateConfig`, `applyConfig`, `getConfig`, `resetConfig` and `setVisible`. Its present example is:

```ts
import { Landmarks3D } from "@tomtom-org/maps-sdk-plugin-landmarks-3d";
const landmarks = new Landmarks3D(map);
landmarks.updateConfig({ color: "#c8b28a" });
```

Do not implement from a search snapshot without checking the actual installed version and current docs. TomTom is worth reconsidering only after an entitled project account demonstrates the required Astana landmarks.

### HERE: the web/mobile distinction is decisive

The [current official feature matrix](https://docs.here.com/style-editor/docs/features-and-modes) assigns detailed building landmarks only to HERE SDK Navigate. Its extrusion feature explicitly includes HERE Maps API for JavaScript. The [Android feature table](https://docs.here.com/here-sdk/docs/android-introduction-feature-list) makes the same distinction between ordinary extrusions and textured landmark support.

HERE's [vector schema](https://docs.here.com/map-rendering/docs/buildings) contains `has_landmark` and `has_3d_model` flags. Those describe source-platform data availability, not a promise that the web renderer supplies every referenced mesh. Neither world map coverage nor Kazakhstan coverage resolves this product boundary. A HERE mobile migration would also change Qala's deployment model and still need an Astana geometry test.

### Google, Cesium, MapTiler and Vexcel: separate the layers

[Google's official country table](https://developers.google.com/maps/coverage) shows Kazakhstan with a single 2D map-tile entry and no Maps JavaScript 3D support. Cesium's [content catalog](https://cesium.com/platform/cesium-ion/content) lists world terrain, OSM buildings and photorealistic partner tiles as separate products. Choosing Cesium or adding a satellite basemap cannot turn unsupported Astana terrain/footprints into captured architecture.

[MapTiler's exact Astana catalog](https://www.maptiler.com/on-prem-datasets/asia/kazakhstan/astana/) advertises OSM vectors, satellite rasters, contours and hillshading. It does not advertise a textured Astana mesh on that page. This is an observation about the advertised catalog, not an assertion about every possible custom commercial order.

[Vexcel's official Cesium announcement](https://cesium.com/blog/2024/06/25/vexcel-cesium/) establishes a genuine reality-mesh product and commercial self-hosted delivery, with coverage emphasized in the United States, Europe, Australia and Japan. The dated 2024 announcement is insufficient to assert current Astana absence or presence. Request an actual coverage polygon, sample and rights before treating Vexcel as a qualified Astana source.

### Bing and Azure: no supported shortcut established

The [Bing geographic coverage documentation](https://learn.microsoft.com/en-us/bingmaps/coverage/geographic-coverage) says free Basic accounts have retired; existing Enterprise service access ends on 30 June 2028. Its Kazakhstan road/geocoding table does not prove textured city-model coverage.

[Azure's current render coverage](https://learn.microsoft.com/en-us/azure/azure-maps/render-coverage) concerns raster/vector road tiles and does not list Kazakhstan. A [2022 Microsoft staff answer](https://learn.microsoft.com/en-us/answers/questions/951844/3d-maps-in-azure-maps) distinguishes Azure extrusions/custom overlays from Bing textured cities. That answer is historical context, not a reliable statement of every current Azure capability. No current official Astana photogrammetry footprint or suitable supported detailed web path was established.

## Credential-free embedding: what the documented interfaces allow

### Yandex Constructor is broader than an iframe, but remains a saved-map interface

The [official Constructor API](https://yandex.com/maps-api/docs/constructor/api.html) supports a script-generated saved interactive map. An API key is optional for that limited interface; omitting it removes search, route-building and panorama controls. Documented parameters cover the saved-map ID, dimensions, container ID, language and scroll behavior.

The documentation does not expose a supported callback giving Qala the map instance, arbitrary runtime Valhalla geometry updates, or selected-place event synchronization. It also does not establish that Constructor supplies API v3/consumer detailed-3D parity. Do not infer 3D support or access internal objects simply because the widget is generated by a script.

The ordinary [share widget](https://yandex.com/support/maps/en/concept/get-map-reference) can embed a location or route. Yandex's [tool overview](https://yandex.com/dev/maps/mapstools/) explains that a route is recalculated for the viewing session. A route generated by the provider is useful in a separate viewer, but does not preserve Qala's supplied Valhalla polyline.

A controlled native map still uses the [API v3 quickstart](https://yandex.com/maps-api/docs/js-api/quickstart.html), which requires an owned key. Its native `YMapFeature` and `YMapMarker` primitives fit Qala's existing state contract. A free license is not keyless access.

The current [Kazakhstan terms](https://yandex.kz/legal/maps_api/ru/) require a qualifying freely accessible project (§4.1.1), preserved attribution (§4.1.3), and allow supplied advertisements (§4.5). Section 5.1.3 excludes real-time monitoring of people, vehicles or other objects, and dispatch services, from free use. Personal navigation may differ from monitoring; obtain provider confirmation or applicable commercial terms before claiming Qala's complete GPS flow qualifies for a free license. Section 5.1.4 also restricts retaining or modifying provider-derived data; Qala's independent Valhalla route should remain separate from Yandex-derived service data. Public availability alone is not sufficient proof of eligibility.

### 2GIS's old no-key FAQ is not a current MapGL entitlement

An [older official FAQ](https://api.2gis.ru/doc/faq/) and [helper page](https://help.2gis.com/question/api2gis) describe no-key/free maps. They concern older APIs/widgets and conflict with current product access documentation. The [current API Platform overview](https://docs.2gis.com/en/api-platform) requires a demo or subscription key, and the [current RasterJS overview](https://docs.2gis.com/en/maps/others/rasterjs/overview) describes charged raster-tile requests and key limits.

The old FAQ is therefore not evidence that current detailed 3D MapGL may be embedded with unrestricted no-key route/pin APIs. No such supported path was found in this investigation.

## Exact owned-key activation paths

**Best immediate native path: 2GIS MapGL, already integrated in Qala.** The current [key-creation instructions](https://docs.2gis.com/en/platform-manager/subscription/keys) lead to the [Platform Manager](https://platform.2gis.ru/en/): sign in, open Dashboard, select Create a Demo Key, enter a name and create it. The free demo may be created once and lasts one month. Configure origin/referrer restrictions for Qala and supply the resulting owned browser key through `VITE_2GIS_API_KEY`; then verify the actual production page. Continued production use needs an appropriate subscription. This path does not require adding another renderer.

**Yandex alternative:** the v3 quickstart links to the [developer account](https://developer.tech.yandex.com/), which currently redirects to Yandex ID authentication for the Maps API console. Select the JavaScript API and Geocoder HTTP package, obtain the owned key, and set its HTTP Referer restriction; the quickstart says activation can take up to 15 minutes. The package and project must satisfy the applicable terms, including the GPS-use question above. This is a potential separate integration, not an existing Qala setting.

Neither examined issuance flow supports anonymous automatic key registration. No account was created, and there is no authorized signed-in project account in this workstream. Account ownership, acceptance of provider terms and paid subscription decisions cannot be replaced by extracting a demo-page key.

## Implementation consequence

Keep one source-neutral route, selection and GPS state contract. Enable the detailed native provider only when its own credentials or authorized dataset exist. Preserve the useful genuinely flat map while access is unresolved; do not turn generic extrusions back on, disguise a fixed widget as the native route map, or label untested global data as accurate Astana architecture.

Before selecting a newly qualified source, inspect Bayterek and alem.ai, plus the Circus and Kazakh Eli counterexamples, after actual geometry loading. Verify the project's own route, markers, pointer/keyboard controls, attribution and true flat mode in the deployed application. Provider-hosted geometry evidence does not by itself validate Qala's authenticated production path.

