# Yandex map implementation and municipal attempt

Historical implementation, superseded by the user's later request to restore the original embedded MapLibre 3D view. The current build uses no Yandex key or external 3D action. See [embedded map restoration](embedded-map-restoration.md) and [its current verification](../../artifacts/embedded-map-verification.json). The implementation and pass counts below describe the earlier keyed-provider iteration.

Implemented on 19 October 2026 following the user's instruction: try Cesium with an authorized municipal mesh; if it fails, choose the best alternative excluding municipal mesh and 2GIS.

## Actual municipal attempt

The real Cesium I3S loader rejected the central municipal service. Fresh 2022 and 2024 layer/root requests returned backend-unavailable error bodies despite HTTP 200. The alternative DIMASH layer required a token. No permitted central-city delivery was configured.

A local northern SLPK control rendered through Cesium 1.146.0, confirming that the engine works. That package does not cover Bayterek or alem.ai, has uncorrected EGM96 heights and no established reuse license. It was not substituted for central Astana or bundled with the application.

[Actual attempt and counters](../../artifacts/municipal-map-attempt.json), [attempt report](municipal-map-attempt.md).

## Selected fallback

**Native Yandex Maps JavaScript API v3 replaces 2GIS.** The 2GIS runtime component, npm dependency, environment setting and container build argument have been removed. The app does not make 2GIS or municipal-service requests.

CityMap loads one active renderer lazily. Recommendations, selected place, the exact Valhalla street polyline and optional GPS stay in their existing shared owner. No assistant, itinerary or route state moves into a provider-specific store.

The native component uses current official types and public APIs: DOM markers with keyboard selection, exact LineString features with simplification disabled, route casing, fit/zoom/recenter/north controls, radians for camera values and a native margin tuple. Flat mode uses the documented `render-3d: off` scheme customization, zero tilt and disabled tilt gestures. It does not merely turn the camera upward.

The visible native viewport reserves the measured itinerary area. This keeps the provider's own attribution and controls above cards without hiding them or guessing internal distribution CSS classes. SDK loading is shared and bounded; failed access, timeouts and context loss expose recovery. Map destruction removes resources and listeners; stale async completion cannot create an abandoned map.

The flat map continues to use OpenFreeMap, with all extrusions hidden. GPS updates its own marker without rebuilding focused place controls. An external Yandex action is explicitly a new-tab link, targeting the selected public place or chosen starting point.

## Why the public widget was rejected

A no-key widget was tested directly and inside the real application. Some standalone captures displayed detailed geometry, but the result could not be reproduced reliably. Actual app trials showed cylinders. The inspected widget had zero tilt and only pan/zoom behaviors; native tilt gestures did not enable the required view. Document load and successful HTTP requests were not geometry proof.

An initial apparent .com/.kz correlation did not survive controlled checks. It is not a supported fix. The widget component and its default-view path were removed instead of shipping another inaccurate 3D preview. [Negative capability evidence](../../artifacts/yandex-widget-verification.json).

## Verification and limits

The native component passed 17 contract checks using its real React code and a local SDK double. Checks cover geometry updates, selection, keyboard camera timing, GPS, true-flat customization, viewport margins, navigation, context-loss recovery and destruction. These are integration contracts, not proof of live geographic content.

A separate actual-network request using a deliberately invalid synthetic key verified visible recovery, disabled unavailable controls, retry, rejected-script cleanup and no unhandled page errors. Official provider-hosted SDK inspection independently verified blue route strokes with white casing and native marker primitives; no example key was transferred.

[Native contract and invalid-key evidence](../../artifacts/yandex-native-contract-verification.json), [primary API implementation reference](yandex-native-implementation.md). The successful owned-key application session remains unverified. Earlier provider landmark observations are candidate-content evidence, not a substitute for that final test.

## Final app checks

The final production bundle passes 23 desktop/mobile browser checks, 9 full-app invalid-key recovery checks and 7 GPS-focus regressions. A covered desktop itinerary control was fixed by anchoring controls above the measured card area. Full-app fallback, reconnect and retry retain the exact route, totals and selected place; one renderer remains active. GPS checks use synthetic browser fixes. [Historical verification scopes and source hashes](../../artifacts/history/yandex-map-implementation-verification.json).

## Activation

Obtain an owned key for the [JavaScript API and Geocoder HTTP package](https://yandex.com/maps-api/docs/js-api/quickstart.html). Configure HTTP Referer restrictions for the application origins, including the localhost origins used for evaluation. Put it in the local `.env`:

```dotenv
VITE_YANDEX_API_KEY=your_owned_browser_key
```

Rebuild with `npm run build` or `docker compose up --build`. Activation can take up to 15 minutes. The browser key is deliberately public to that origin; private voice/model keys remain server-side. Do not paste private credentials into chat or reuse provider documentation credentials.

The [Kazakhstan terms](https://yandex.kz/legal/maps_api/ru/) and personal-navigation versus free monitoring qualification remain applicable. English and Russian provider map labels are supported; Kazakh controls currently use Russian provider labels. Labels use the SDK locale selected at initial load.

Without a key, the app stays genuinely flat and useful for routing. Detailed embedded 3D is pending owned access, actual landmark checks, exact overlays, attribution, recovery and target-device performance verification. The implementation does not claim a perfect or photorealistic full-city model.
