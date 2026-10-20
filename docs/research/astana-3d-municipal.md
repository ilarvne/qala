# Astana municipal and local-vendor 3D data investigation

Checked 19 October 2026, approximately 11:54–12:00 UTC. This workstream covers municipal datasets and Kazakhstan suppliers. It does not change app source files or publish any downloaded model.

## Finding

**Astana already has a genuine textured photogrammetric city model. Its public portal exposes substantial model metadata and six real downloadable scene packages. The citywide streaming backend is currently failing, none of the six downloadable packages covers Bayterek or alem.ai/EXPO, and an open reuse license has not been established.**

This is stronger evidence than a vendor brochure or a screenshot: the municipal Web Scene declares 374 `IntegratedMeshLayer` references, and binary SLPK payloads decode to actual `IntegratedMesh` geometry, textures, coordinate systems and hierarchical mesh metadata. It is not evidence that the whole city currently renders correctly, that the model meets survey accuracy, or that it can be republished in this app. [Municipal scene data](https://gis.esaulet.kz/portal/sharing/rest/content/items/b535181687714acb87d95950844aed6a/data?f=pjson)

## 1. The municipal model and its present failure

The public [Astana Geographic Information Center](https://gis.esaulet.kz/portal/apps/experiencebuilder/experience/?id=b9f6d12fcdc644f6944a96d5c42b915f) is an ArcGIS Enterprise portal. Its live [portal metadata](https://gis.esaulet.kz/portal/sharing/rest/portals/self?f=pjson) names it “Геоинформационный центр города Астаны” and credits KazAeroSpace, 2021. KazAeroSpace's [own project entry dated 13 June 2022](https://kazaerospace.kz/projects/card/9) identifies the Nur-Sultan geoportal and the city's Architecture and Urban Planning Department. The [Astana Invest description](https://investastana.kz/astana-invest/press-center/news/kazaerospace_rezident_tekhnoparka_innovatsionnogo_klastera_nazarbayev_university_i_sez_astana_tekhno/) also identifies KazAeroSpace as the developer of the Astana digital twin established in 2021.

The portal is responding normally; its ArcGIS Server web adapter is responding with application errors. HTTP status alone would give a false positive:

| Live request | HTTP | Actual result |
|---|---:|---|
| [Portal metadata](https://gis.esaulet.kz/portal/sharing/rest/portals/self?f=pjson) | 200 | Valid public portal JSON |
| [Main scene metadata](https://gis.esaulet.kz/portal/sharing/rest/content/items/b535181687714acb87d95950844aed6a?f=pjson) | 200 | Valid public Web Scene, last modified 10 December 2024 |
| [Main scene content](https://gis.esaulet.kz/portal/sharing/rest/content/items/b535181687714acb87d95950844aed6a/data?f=pjson) | 200 | Valid scene JSON with 374 mesh references |
| [Server service directory](https://gis.esaulet.kz/server/rest/services?f=pjson) | 200 | `status: error`; no backend server machine reachable |
| [Example integrated-mesh layer](https://gis.esaulet.kz/server/rest/services/Hosted/Sector289_1_8/SceneServer/layers/0?f=pjson) | 200 | Same backend error |
| [Example mesh root node](https://gis.esaulet.kz/server/rest/services/Hosted/Sector289_1_8/SceneServer/layers/0/nodes/root?f=pjson) | 200 | Same backend error |
| [Coverage polygon layer](https://gis.esaulet.kz/server/rest/services/Hosted/Granicy_obnovleniya_2022/FeatureServer/1?f=pjson) | 200 | Same backend error |

The exact Russian server message says no server computer could be reached and asks the user to contact the administrator. Plain HTTP produces a separate error saying the server accepts HTTPS only. These results explain why an indexed REST directory does not prove a usable live dataset. They establish an infrastructure failure during this check; they do not establish permanent shutdown or an intentional access restriction.

### Model versions and coverage evidence

Anonymous portal searches returned **407 Scene Service items**, four Web Scenes and six Scene Packages. The main scene is `b535181687714acb87d95950844aed6a`, “3D Карта города Астаны (основная)”. Its mesh groups are:

| Group label | Integrated mesh references | Example service |
|---|---:|---|
| 2020 photorealistic model | 157 | `Hosted/i3s_WSL1/SceneServer/layers/0` |
| 2021 photorealistic model | 69 | `Hosted/Sector181_i3s/SceneServer/layers/0` |
| 2022 photorealistic model | 91 | `Hosted/Sector289_1_8/SceneServer/layers/0` |
| 2024 photorealistic model | 57 | `Hosted/Sector_422_1_8/SceneServer/layers/0` |
| Total | **374** | |

These are reference counts, not square kilometres, distinct capture campaigns, complete buildings, or non-overlapping coverage. The 2020 group has 158 children but only 157 integrated meshes; counting every child as a mesh would be incorrect. Year labels and item timestamps are not independently verified flight dates. [Scene JSON](https://gis.esaulet.kz/portal/sharing/rest/content/items/b535181687714acb87d95950844aed6a/data?f=pjson)

The scene uses Web Mercator (`3857`/`102100`), metre heights and a gravity-related height model. Individual downloaded packages instead use geographic WGS84 (`4326`) with an explicitly specified vertical CRS. Only 19 of the 407 service registry entries contain an extent. The broad `Build_151222` extent encloses much of Astana and both requested landmarks, but its registry extent does not prove landmark geometry fidelity or even that it is the correct photorealistic layer. Sector coverage polygons could identify the exact Bayterek and EXPO tiles once their server is restored. [Scene services search](https://gis.esaulet.kz/portal/sharing/rest/search?f=pjson&q=type%3A%22Scene%20Service%22&num=100), [Build item metadata](https://gis.esaulet.kz/portal/sharing/rest/content/items/f426292d253c4462a845e790dac23208?f=pjson)

## 2. Real public package downloads

All six packages returned HTTP 200 to `HEAD`, real binary content lengths and SLPK filenames. Bounded HTTP 206 requests allowed decoding `3dSceneLayer.json.gz` from every package. This proves their actual mesh format and spatial extent without downloading several gigabytes.

| Package and download | Bytes | Actual I3S version | Horizontal extent, longitude/latitude | Item uploaded |
|---|---:|---:|---|---|
| [Sector1_9_20cm_FT1](https://gis.esaulet.kz/portal/sharing/rest/content/items/426defe5ab154d978d3fce97666db526/data) | 21,291,363 | 1.5 | 71.410160, 51.206086 → 71.535578, 51.223936 | 14 February 2022 |
| [Sector6_8_20cm_FT1](https://gis.esaulet.kz/portal/sharing/rest/content/items/87c8f46cbc96452597ec985df588e95c/data) | 165,308,332 | 1.5 | 71.394180, 51.023393 → 71.432385, 51.045601 | 14 February 2022 |
| [Sector_jerleu_1_1_8](https://gis.esaulet.kz/portal/sharing/rest/content/items/ab9aef1f42874124a804df89d09a668c/data) | 225,320,818 | 1.8 | 71.319024, 51.268596 → 71.323343, 51.272319 | 15 July 2024 |
| [Sector_Jerleu_1_8](https://gis.esaulet.kz/portal/sharing/rest/content/items/496a79005cbe4e9d982a5a82cff94d7b/data) | 1,015,650,999 | 1.8 | 71.321825, 51.275266 → 71.331590, 51.281915 | 15 July 2024 |
| [Sector1_9_20cm](https://gis.esaulet.kz/portal/sharing/rest/content/items/6cc4e9566c7049cbab74af91b067516d/data) | 4,300,189,724 | 1.5 | 71.414731, 51.172471 → 71.646404, 51.292428 | 14 February 2022 |
| [Sector15_1_2_slpk](https://gis.esaulet.kz/portal/sharing/rest/content/items/ec2b846a96354be2855999c6b07af34e/data) | 5,603,249,472 | 1.5 | 71.391357, 51.183068 → 71.421529, 51.194577 | 9 November 2022 |

**None of these extents contains Bayterek or alem.ai/EXPO.** They are samples from northern Astana, a southern strip, and the far northwest. Their upload dates are not capture dates, and `20cm` in a filename is not an independently measured accuracy result.

The four older packages explicitly describe textured meshes produced by ContextCapture. Their metadata specifies triangular geometry, normals, UVs, JPEG textures, hierarchical mesh pyramids, WGS84 horizontal coordinates and vertical CRS `5773` (EGM96 height). The two 2024 packages explicitly describe a Bentley ContextCapture reality mesh and declare I3S 1.8, Draco geometry, JPEG/DDS texture formats and vertical CRS `3855` (EGM2008 height). That vertical-datum difference matters when combining packages or placing routes and POIs.

The smallest complete archive was downloaded for local research and validated with Python `zipfile`: 21,291,363 bytes, 6,681 archive entries, SHA-256 `f4f281c792341b6466f072463093b94c91978647987a5d597e4657c97d4ec941`. It contains real mesh node documents, geometry buffers and textures. Its root bounding sphere centres at approximately 71.472860° E, 51.215905° N. It has **not been visually rendered by this workstream**.

Local binary: `artifacts/private/research/astana-3d/Sector1_9_20cm_FT1.slpk`. That directory is already ignored by Git. Raw metadata and request evidence are stored beside it. No model binary was added to source control or published.

The public package query is [reproducible here](https://gis.esaulet.kz/portal/sharing/rest/search?f=pjson&q=type%3A%22Scene%20Package%22&num=100). A Scene Service item is a different object: three representative service `/data` endpoints returned zero-length bodies, so a gigabyte item size alone is not a downloadable SLPK.

### Licensing and format qualification

Every tested package is marked `access: public`; every package's `licenseInfo` is null. The main scene and tested mesh service items likewise lack an explicit reuse license. Public viewing and downloading do not establish commercial embedding, redistribution, conversion, derivative-work or self-hosting rights. Those rights must be obtained from the actual rights holder before shipping these assets. The portal credits a developer, which does not by itself identify the legal data owner. [Example package metadata](https://gis.esaulet.kz/portal/sharing/rest/content/items/426defe5ab154d978d3fce97666db526?f=pjson)

Do not treat SLPK, I3S 1.5, I3S 1.8 and 3D Tiles as interchangeable. A renderer must support the actual I3S version or the package must be upgraded/converted and validated. These reality meshes also do not establish CityGML LoD2/LoD3 semantic buildings. No public CityGML or authoritative LoD2/LoD3 citywide dataset was verified in this workstream.

## 3. Actionable acquisition path

**First choice: obtain the existing municipal model through the city's Architecture and Urban Planning Department and KazAeroSpace.** The project exists, has multiple year-labelled mesh groups, and has an identified original developer. Request a licensed delivery or an agreed, supported streaming endpoint rather than relying on the presently failing public server. KazAeroSpace publishes [a contact page](https://kazaerospace.kz/contacts) and the [original project description](https://kazaerospace.kz/projects/card/9). No inquiry was sent during this research.

A useful acquisition request would specify:

1. An exact coverage polygon and a tile/sector index. Require Bayterek and the alem.ai/EXPO sphere, surrounding streets and the proposed route area in the evaluation sample.
2. A textured photogrammetric mesh or verified detailed building models, plus actual sample screenshots and an inspectable model. Footprint extrusion is insufficient for the rejected landmarks.
3. Actual capture dates per sector, processing dates, horizontal and vertical CRS, geoid/transformation details, texture resolution, ground sampling distance, independent checkpoint accuracy and known holes/artifacts.
4. Delivery as validated I3S 1.8/SLPK or 3D Tiles, complete texture assets, lower levels of detail, and terrain alignment. Ask whether building IDs or a separate pickable building/POI layer are available; a continuous mesh does not automatically provide useful object IDs.
5. Written rights for web display, domain/app use, caching, conversion and self-hosting; specify commercial or hackathon use as appropriate, attribution and duration. Ask for update terms and whether private/restricted layers must be excluded.
6. A browser acceptance sample before purchasing: orbit both landmarks, inspect roof and facade shape, check ground alignment, verify route/POI placement, test mobile performance and record holes. Obtain a supported endpoint or a licensed independent copy before treating this as production data.

If municipal delivery is unavailable, **KazAeroSpace's own survey operation or KazUAV are concrete custom-acquisition candidates**, not verified suppliers of a ready, licensed citywide Astana dataset. [KASMapping](https://www.kasmapping.kz/) identifies KazAeroSpace's aerial mapping system and explicitly offers photorealistic terrain modelling. Its published resolution and positioning figures are equipment/vendor claims, not measured quality of these downloaded packages. [KazUAV's service page](https://kazuav.kz/services) offers aerial surveying, terrain/building 3D models, DEM/DTM products and geoportals; no public current citywide Astana mesh inventory or price was established.

The national space company is a weaker stock-data lead: [Geoscan's original December 2016 project page](https://www.geoscan.ru/ru/blog/3d-model-centra-astany-0) establishes a genuine aerial-survey demonstration of central Astana with Kazakhstan Garysh Sapary. Its age and presentation as a demonstration do not establish a current reusable city service. [Garysh Sapary's current photogrammetry page](https://www.gharysh.kz/uslugi/fotogrammetriya/) primarily describes satellite orthorectification, terrain models and mosaics; these are not sufficient proof of detailed urban landmark meshes.

## 4. Rejected substitutions

- Astana's [3D tours page](https://astana.kz/en/tours) and [the original 3D Astana tour producer's description](http://cityscanner.ru/astana) concern linked panoramic viewpoints. They are not free-camera city meshes.
- General building layers, terrain, satellite orthophotos and cadastral boundaries do not prove recognizable landmark geometry.
- A model built from OSM footprints and satellite texture references does not satisfy the requested landmark fidelity without an independently verified geometric source. Google Earth imagery also cannot be presumed freely reusable for a new model.
- The original engineer's [2024 interview](https://intranews.kz/old/intervyu-s-vedushchim-inzhenerom-gis-o-cifrovyh-dvoynikah) supports project provenance but its centimetre-accuracy claim was not independently tested here.

## Reproducibility and search accounting

The attached [structured evidence](astana-3d-municipal-evidence.json) records all six package metadata documents, every mesh URL grouped by year, observed failures and material limitations. The [search audit](astana-3d-municipal-search-audit.json) records 14 successful Exa searches: **101 requested result slots, 96 returned URL slots and 71 distinct URLs**, including irrelevant results filtered during review. One initial malformed request asked for eight result slots but returned a schema error and no results; it is recorded separately and not counted as eight reviewed sources. Full-page fetches and direct live API probes are additional checks, not additional Exa search result slots. This accounting does not claim that every distinct URL was read in full.
