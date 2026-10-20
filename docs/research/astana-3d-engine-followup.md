# Astana 3D map: production engineering follow-up

Research date: 19 October 2026. This is an additional evidence pass for the implementation decision in [the map plan](astana-3d-map-plan.md), not a claim that the application now has a full-city photorealistic dataset.

## Newly checked open service

[Re:Earth Buildings](https://github.com/reearth/reearth-buildings) now supplies an accessible, credential-free [3D Tiles 1.1 endpoint](https://buildings.reearth.land/tileset.json). The root returned HTTP 200, valid asset metadata and attribution during this pass. Its maintainers explicitly describe generated Overture footprints and a height cascade that can estimate dimensions from floors, class or footprint area. It therefore fails this project's architectural-fidelity requirement. Replacing MapLibre extrusions with those tiles would change the transport and renderer while retaining the underlying information gap.

The primary repository distinguishes service-code licensing from the ODbL-derived output and requires attribution. These terms are useful for a general massing visualization; they do not demonstrate a surveyed central-Astana model or the sphere/lattice geometry the user requested. The service was discovered after the earlier report and is added as an assessed alternative, not silently omitted.

## Renderer requirements established from primary documentation

[Cesium's native I3S interface](https://cesium.com/learn/cesiumjs/ref-doc/I3SDataProvider.html) accepts scene-layer endpoints and streams content through its internal tilesets. Its documented version support starts at I3S 1.6; Qala's earlier local test separately demonstrated decoding one older 1.5 package. That test must not be generalized to every 1.5 export. Test each actual delivery, including textures and lower detail levels, before accepting it.

For an orthometric source, use the geoid corresponding to its declared vertical reference system. The I3S interface exposes `geoidTiledTerrainProvider` for this conversion. [Esri's integration tutorial](https://developers.arcgis.com/cesiumjs/layers/add-an-integrated-mesh/) warns that missing or invalid correction can cause mesh and terrain to clip. The northern Astana sample declares EGM96; newer public packages declare EGM2008. An example EGM2008 URL is not a universal fix for both.

[GroundPolylineGeometry](https://cesium.com/learn/cesiumjs/ref-doc/GroundPolylineGeometry.html) ignores input heights. A street route drawn on an integrated mesh can follow a roof if the selected clamping policy receives roof geometry. Keep Valhalla's authoritative two-dimensional path unchanged, obtain a compatible ground DTM or qualified height samples, and verify entrances, underpasses and crossings. Height sampling from a visible surface is not proof of pedestrian traversability. Keep suggested straight connections visually distinct from street-routed geometry, as the current application does.

Follow the [official Vite example](https://github.com/CesiumGS/cesium-vite-example) when a qualified mesh is available: named module imports, matching self-hosted Workers/ThirdParty/Assets/Widgets, and a defined asset base. Do not rely on an unpinned public CDN in the production app. [Explicit rendering](https://cesium.com/learn/cesiumjs/ref-doc/Scene.html) reduces idle work but requires render requests after external state changes. Lazy-load the selected engine, destroy its WebGL resources on replacement, release listeners and observers, and keep recommendation/navigation state in the shared React owner.

Bound image resolution and tile caches by device class; configure screen-space error based on measured quality and memory. Do not turn every high-cost setting on. Tile failures and sustained loading need a retry path that keeps selected stops and routes. Preserve attribution, keyboard focus, reduced-motion settings and measured card insets. Keep true flat 2D as a separate depth-free presentation; do not label a top-down textured building scene as flat 2D.

## Acceptance gates

A production map source must pass these gates in order. A failed gate is a reason to hold that source out of the main map, not a reason to invent missing data.

| Gate | Required evidence |
| --- | --- |
| Source and permission | Named data owner/licensor, permitted public web display, attribution and hosting/caching/conversion terms |
| Geographic coverage | Actual scene content around Bayterek and alem.ai, surrounding streets and the walking corridor; registry extents alone do not pass |
| Geometry | Real sphere/opening at alem.ai, gold orb and white lattice at Bayterek, appropriate surrounding building detail; multiple close and wide views |
| Alignment | Known horizontal CRS, vertical datum, ground reference, capture date and measured checkpoint method |
| Delivery | Successful root, node, geometry and texture requests, supported formats and valid lower detail levels |
| Interaction | Shared POI selection, exact street route, optional GPS, fit/recenter/north/zoom, clean 2D/3D switch |
| Lifecycle | One active map context, cancellation of stale loads, retry without state loss, cleanup after repeated switches |
| Usability and performance | Desktop and mobile real-pointer checks, visible controls above itinerary cards, stable frame time and bounded memory on a stated test device |

The proposal is not complete merely because a globe renders. Neither an engine benchmark on a northern sample nor a provider's catalog promise establishes any of the central-landmark gates.

## Scope and audit

This workstream made five successful Exa searches: 44 requested result slots, 44 returned entries, 44 distinct result URLs. These are discovery counts, not 44 independently validated sources. Two earlier calls failed local connector argument validation before a search and are excluded. Selected primary documents and the Re:Earth service root were inspected directly. [Machine-readable audit](evidence/astana-engine-followup.json).
