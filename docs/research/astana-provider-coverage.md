# Astana 3D map coverage

Verified 19 October 2026. The acceptance test is Nur Alem's actual curved sphere and Bayterek's sphere and lattice, not a tilted extrusion of building footprints.

This is the initial two-landmark investigation. The [subsequent deep study](astana-3d-map-plan.md) adds wider 2GIS coverage failures, directly verified Yandex SDK geometry, municipal mesh files and a local I3S compatibility pilot. Earlier unverified Yandex SDK statements below describe that initial stage; use the [new SDK report](astana-3d-sdk.md) for the current decision.

## Decision

Use 2GIS MapGL with the project's own authorized Map Tiles API key. Its public SDK playground directly demonstrated detailed models for both landmarks with the default map style. Do not copy a key from a consumer site, playground, or example. The project needs a valid project key before its embedded SDK can be verified end to end.

## Direct visual verification

| Provider | Nur Alem / Alem AI | Bayterek | Integration consequence |
| --- | --- | --- | --- |
| 2GIS MapGL, official playground | Verified curved sphere, glass panel mesh, top aperture, pedestal and detailed surrounding buildings | Verified golden sphere, open metal lattice and base | Appropriate SDK candidate; both target models are supplied by the map itself |
| Yandex consumer / widget | Root agent verified a faint but real sphere mesh in the public widget | Official Yandex curated 3D collection explicitly lists Bayterek | Useful no-key viewer; a cross-origin widget does not provide this app's route and marker event integration |
| Mapbox public Standard demo | Root agent observed a cylinder at Nur Alem | Not tested in this workstream | No demonstrated improvement for the failing landmark |
| Google | Official coverage table lists Kazakhstan with 2D tiles only and no Maps JavaScript 3D surface coverage | Same country coverage limitation | Not selected for this project |

2GIS is detailed architectural modeling, not a guarantee of photogrammetry or complete city-wide textured meshes. Ordinary buildings may still use footprint extrusions.

### Other provider checks

- [Google's current country coverage table](https://developers.google.com/maps/coverage) lists Kazakhstan without 3D surface coverage. [Google's 3D coverage documentation](https://developers.google.com/maps/documentation/javascript/3d/coverage) distinguishes worldwide terrain from the limited surface mesh coverage. A Cesium renderer cannot supply missing source geometry.
- [Mapbox Standard's official live demo at Alem AI](https://labs.mapbox.com/standard-style/?lightPreset=day#17/51.08921/71.41607/-18/58) rendered the same cylinder in the research browser. Mapbox supports detailed landmarks in selected cities, but its [general landmark announcement](https://www.mapbox.com/blog/global-cities-3d-landmarks) does not establish Astana coverage.
- Public ArcGIS search returned six Astana DIMASH scene services; their item/service access returned `403`, `SB_0005`, subscription disabled. The public “KazUAV map for Astana Innovations” web scene returned no operational layers. Municipal `gis.esaulet.kz` lists I3S services, but live service requests timed out during this investigation. These are not verified working or licensed alternatives for this release.

### Reproduce 2GIS

1. Open the [official Map Tiles API playground](https://platform.2gis.ru/en/playground/mapgl/), which redirects to `/playground/mapgl`. It works without signing in.
2. Leave **Map style ID** blank to use its default style.
3. Set **Latitude** to `51.08921` and **Longitude** to `71.41607` for Nur Alem.
4. Use the `+` control about seven times from the initial city-wide view, then select the round **3D** control.
5. Wait for model assets to finish loading before assessing geometry.
6. For Bayterek change latitude to `51.1283` and longitude to `71.4305`; keep the close zoom and 3D mode. Bayterek initially appeared as a plain cylinder while assets loaded, then changed to its detailed model.

Evidence captured directly from the official playground:

- [Nur Alem sphere](../../artifacts/screenshots/2gis-preview-nuralem.png)
- [Bayterek sphere and lattice](../../artifacts/screenshots/2gis-preview-bayterek.png)

The 2GIS consumer site redirected the research browser to a CAPTCHA. The SDK playground supplied stronger relevant evidence without attempting to solve or bypass that challenge. No playground credentials were extracted or reused.

### Yandex sources and limits

- [Official Astana landmarks in 3D collection](https://yandex.kz/maps/discovery/dostoprimechatelnosti-astani-v-3d/) lists Bayterek, Astana Opera, Nursultan Mosque, Khan Shatyr, Palace of Peace and Reconciliation, Roza Baglanova concert hall, and the Triumphal Arch. It does not list Nur Alem; that omission alone does not prove absence.
- [Public Nur Alem widget](https://yandex.kz/map-widget/v1/?ll=71.41607%2C51.08921&z=18&tilt=0.7) was separately inspected by the root agent, with a real sphere mesh visible.
- [Yandex JS API v3 quick start](https://yandex.com/maps-api/docs/js-api/quickstart.html) requires an API key and configured HTTP Referer restrictions. Consumer/widget coverage does not establish that the same model is available through a project API key; that SDK equivalence was not verified here.
- [Custom vector layers](https://yandex.com/maps-api/docs/js-api/object/layers/custom-layers.html) and [Deck.gl integration](https://yandex.com/maps-api/docs/js-api/examples/cases/deck-gl-integration.html) require the experimental custom-layer option to be enabled by support. They are not a key-free drop-in way to import a landmark model.

## 2GIS integration references

- [Getting started](https://docs.2gis.com/en/mapgl/start/first-steps): the supported library is `@2gis/mapgl`, or the hosted `https://mapgl.2gis.com/api/js/v1`. Supply an own Map Tiles API access key. The documentation explicitly permits exploring the hosted playground without authorization.
- [Map API overview](https://docs.2gis.com/en/maps/overview): keys are managed in Platform Manager; demo access is limited to one month and request limits, while production requires the appropriate subscription. No account or subscription was created for this investigation.
- [Configured layers](https://docs.2gis.com/en/maps/styles/layers/configured/mapgl): ordinary buildings have 3D building layers; major attractions use **Model 3D** and **Immersive Model 3D** layers.
- [3D models](https://docs.2gis.com/en/mapgl/map-style/immersive/models): MapGL supports actual glTF/GLB mesh models. Graphics presets control model layers, but do not disable built-in buildings represented as raised polygons. Therefore a flat view should handle both mesh and extrusion layers.
- [Map reference](https://docs.2gis.com/en/mapgl/reference/Map): `hideLayers({ type })` / `showLayers({ type })` can operate by layer type. Hiding `model`, `polygonExtrusion`, `lineExtrusion`, and `polygon3d`, then calling `setPitch(0, { animate: false })`, was directly verified on the official playground: all vertical geometry and trees disappeared, while a small 2D landmark icon remained. Showing those types and restoring pitch restored 3D. `setPitch(0)` by itself does not remove 3D geometry.
- [Release notes](https://docs.2gis.com/en/mapgl/releases): v1.61.0 extended the `error` event with `webglcontextlost`, `invalidtilekey`, and `styleloaderror`. Handle failure explicitly and preserve the working fallback map.

Exa search accounting: `sources_reviewed: 70` result slots across 14 searches, including overlapping results and one rejected irrelevant coordinate search; this is not a count of unique validated sources. Conclusions above are based on linked primary documentation and direct browser observations.

Camera behavior checked on the official playground: `fitBounds(bounds, { animation: { animate: false } })` updates center and zoom synchronously and resets pitch to zero. Saving the original center, zoom, rotation, and pitch, computing the fit, and restoring the saved values with `{ animate: false }` in the same synchronous call returned the exact original camera before the next frame. Retargeting zoom with `{ animate: false }` cancelled an active long zoom animation and the new value remained stable.
