# Astana 3D map: expanded findings and implementation decision

> Later implementation: the user excluded 2GIS after an actual municipal Cesium attempt failed. Native Yandex Maps v3 is now implemented; owned-key activation remains pending. The public widget failed its in-app geometry gate. See [current implementation](yandex-map-implementation.md). Recommendations below retain their original research context.

Checked 19 October 2026. This additional pass used Exa for **252 returned discovery results across four workstreams**, deduplicated to **216 exact result URLs**. Direct municipal/ArcGIS APIs, provider documentation, model metadata and supplier records were checked separately. Those counts do not represent 216 validated datasets. [Source matrix](../../artifacts/astana-3d-source-matrix.json).

## What to implement

**Use the existing native 2GIS integration with the project's own Map Tiles key for the immediate product. Obtain a permitted central-Astana municipal mesh and stream it natively through Cesium for the photorealistic version.**

The wider investigation found useful acquisition leads but no newly qualified, credential-free source that supplies accurate central-city architecture and Qala's route/selection interaction together. An owned provider key or a qualified data delivery remains an actual dependency. This research does not establish a perfect city model or complete the application's authenticated 3D verification.

2GIS is the strongest already-observed immediate option: its actual SDK rendered detailed Bayterek and alem.ai models in the earlier tests. The same tests found two gaps: Circus stayed cylindrical and Kazakh Eli's column was not visible in tested views. Calling every building accurate would be unsupported. The project's current integration still needs a valid owned-key application session. [Landmark tests](astana-3d-sdk.md), [official key instructions](https://docs.2gis.com/en/platform-manager/subscription/keys).

## What the expanded search added

| Candidate | Actual new evidence | Consequence |
| --- | --- | --- |
| Municipal alternate hosts | All 407 public Scene Service items point to the same municipal backend; all four public scenes were checked for alternate mesh hosts. Fresh mesh requests return application errors despite HTTP 200. | No overlooked working alternate host found in that catalog. |
| Astana_DIMASH_tower | Six real ArcGIS layer endpoints require tokens; associated metadata reports a disabled subscription. Four package downloads return 403. | Central registry extents are leads, not accessible geometry or rights. |
| Historical central photogrammetry | Geoscan documents a real central-Astana UAV model made with Kazakhstan Gharysh Sapary support in 2016. | A concrete archive/survey lead; no public asset or current alem.ai coverage established. |
| Current local suppliers | KazAeroSpace/KASMapping and other Kazakhstan survey operators describe relevant capture and mesh deliverables. The city department and current supplier contacts are identified. | Request the actual central pilot and the real imagery/mesh licensor. |
| GIS copyright certificate | The supplier's accessible certificate registers a computer program. | Software authorship does not establish permission for aerial mesh content. |
| International reality-mesh suppliers | Vantor, Airbus, Hexagon and Vexcel have genuine products; some support new capture. | No exact Astana inventory, dated landmark sample or applicable delivery license verified. |
| Marketplace city and landmarks | Recent city/Nur Alem models exist, but export access and rights are unverified. A permissive Bayterek model has schematic geometry. | Polygon counts and preview availability do not pass accuracy/rights gates. |
| TomTom | A genuine JS GLB landmark plugin exists. | Private Preview entitlement and Astana coverage proof are still required. |
| HERE | Official feature matrix assigns detailed landmarks to native Navigate; the web JS product supports extrusions. | Its broad geographic coverage does not solve this web map. |
| Re:Earth Buildings | Credential-free 3D Tiles endpoint actually responds. Source code describes Overture footprints and height estimation. | Useful general massing, but it repeats the rejected information deficit. |
| Yandex no-key interfaces | Share/Constructor widgets have limited documented interfaces. | No demonstrated native contract for exact Valhalla geometry and synchronized place events. |

The municipal collection remains a substantive positive lead: its main scene references 374 integrated meshes, and six public packages contain real geometry. The available package extents do not contain Bayterek or alem.ai; the northern package rendered in the earlier prototype cannot serve as evidence for those landmarks. [Original municipal evidence](astana-3d-municipal.md), [actual scene content](https://gis.esaulet.kz/portal/sharing/rest/content/items/b535181687714acb87d95950844aed6a/data?f=pjson).

## Access paths and qualifications

For 2GIS, an owner signs into Platform Manager, creates the one-time, one-month demo key or obtains a subscription, enables the appropriate Map Tiles access and restricts browser origins. Qala already reads `VITE_2GIS_API_KEY`. No account was created and no documentation/demo credential was borrowed. A fresh frontend build and integrated landmark/route/control test are required after supplying the owned key. [Official activation path](https://docs.2gis.com/en/platform-manager/subscription/keys).

Yandex API v3 remains a credible alternative with demonstrated distinctive geometry. It also requires an owned key. Its [Kazakhstan terms](https://yandex.kz/legal/maps_api/ru/) restrict free real-time monitoring; personal navigation may differ, so provider confirmation or applicable commercial terms are needed before claiming the complete GPS flow qualifies free. Consumer-map textures and actual SDK materials also remain different evidence. [Provider follow-up](astana-3d-provider-followup.md).

For photorealistic data, the concrete first request goes to the [city Architecture and Urban Planning Department](https://www.gov.kz/org/astana-saulet?lang=ru) and [KazAeroSpace's current contacts](https://kazaerospace.kz/contacts). Ask them to identify the content licensor and provide a central evaluation sector, not merely a software license or scene catalog record. The [prepared request](astana-3d-data-request.md) includes capture dates, a coverage polygon, horizontal/vertical CRS, compatible ground data, geometry/textures/LOD, measured checkpoints and public web/caching/conversion terms. It has not been sent.

## Production architecture and release gates

Keep recommendations, selected place, exact street geometry and opt-in GPS in the shared application state. Lazy-load one active renderer. Use native I3S for a qualified municipal delivery; convert only for a demonstrated compatibility or delivery need. Serve version-matched workers and decoding assets locally, bound tile caches and device resolution, and clean up stale requests, observers, listeners and WebGL resources.

The height system is part of accuracy. Existing packages use different geoids; do not apply an arbitrary EGM2008 correction to an EGM96 source. Street overlays need compatible ground heights and verification at crossings and underpasses. Clamping blindly onto a visible integrated mesh can put a walking route onto a roof. True flat 2D must remove depth layers. These requirements and their primary documentation are in the [engineering report](astana-3d-engine-followup.md).

Promote a source into the main map only after permission, actual central coverage, landmark fidelity, CRS/ground alignment, streamed delivery, shared interactions, cleanup/recovery and stated-device performance all pass. The existing application remains flat without provider access; this research has not changed that state or added another unqualified map.

## Full reports and audit

- [Municipal catalogs, alternate hosts and actual response bodies](astana-3d-municipal-followup.md)
- [Provider capabilities, access paths and current regional terms](astana-3d-provider-followup.md)
- [Suppliers, real model metadata and acquisition route](astana-3d-acquisition-followup.md)
- [Renderer, height, route and lifecycle requirements](astana-3d-engine-followup.md)
- [Machine-readable candidate matrix](../../artifacts/astana-3d-source-matrix.json)

Search accounting: municipal 60 slots/results, providers 60, acquisition 88, engine/integration 44; 27 successful queries total. Deduplication across the four result lists yields 216 exact URLs. Failed connector argument-validation calls returned no results and are excluded. Model/API and service checks are not added to Exa counts. Private certificate/thumbnail caches and downloaded research mesh are excluded from the submission archive. The investigation covers examined public and advertised sources; it cannot exhaust private catalogs, unpublished deliveries or future provider coverage.
