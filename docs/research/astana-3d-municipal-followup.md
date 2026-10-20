# Astana municipal mesh: alternate-host and acquisition follow-up

Checked 19 October 2026. This extends [the first municipal investigation](./astana-3d-municipal.md); it does not replace the proven package/extent results there. [Machine-readable evidence](./evidence/astana-municipal-followup.json) contains exact requests, body-level errors, source URLs, package-access checks and search accounting.

## Result

**No functioning public central-Astana photorealistic mesh endpoint was found. No new mesh reuse permission was established.** A potentially relevant ArcGIS Online collection was discovered and tested, but its actual services require authentication and its subscription is disabled. The municipal portal still responds; its streaming server still returns an application error. The strongest new acquisition evidence is the original supplier's published copyright certificate for its GIS software, with an important distinction: that certificate does not grant rights to the aerial mesh data.

The immediate implementation decision remains unchanged: use an authorized map SDK whose Astana landmark models have been visually verified, or obtain a licensed municipal mesh endpoint/package. The discovered public metadata is useful for requesting access; it is not a usable replacement dataset.

## 1. The municipal catalog has no overlooked alternate scene host

The anonymous municipal search was paginated through **all 407 Scene Service items**, including the last seven entries. Every service URL points to **`gis.esaulet.kz`**. All four public Web Scenes were fetched and their referenced layer hosts inspected. The three city-model scenes refer to the same municipal host for city layers; their other hosts are Esri basemap and terrain services. The default scene contains only Esri basemap/terrain references. No alternative host for the municipal reality mesh appeared in these public catalogs. This is a bounded catalog result, not a claim that no private or unindexed delivery exists. [Scene Service catalog](https://gis.esaulet.kz/portal/sharing/rest/search?f=pjson&q=type%3A%22Scene%20Service%22&num=100), [main Web Scene content](https://gis.esaulet.kz/portal/sharing/rest/content/items/b535181687714acb87d95950844aed6a/data?f=pjson)

Fresh direct requests to the public service directory, server info and `Sector289_1_8/SceneServer/layers/0` all returned **HTTP 200 with an error body** saying that no backend server computer could be reached. They did not return a valid scene layer definition, mesh root or geometry. A catalog entry marking the API active therefore does not prove availability. [Live service directory](https://gis.esaulet.kz/server/rest/services?f=pjson), [tested layer](https://gis.esaulet.kz/server/rest/services/Hosted/Sector289_1_8/SceneServer/layers/0?f=pjson)

The public portal's federation-list endpoint returned ArcGIS error `403 GWM_0003`. That check stopped at the permission boundary. No authentication workarounds, private-host scans, credential discovery or vendor demo tokens were used.

**What this adds:** the earlier report counted the service catalog and inspected the main scene. This follow-up explicitly checks the complete set of service URL hosts and every public scene's host references. The negative result is stronger than checking one representative service URL, but does not resolve the server outage or data rights.

## 2. New ArcGIS Online lead: Astana_DIMASH_tower

Direct ArcGIS Online search found a collection under owner `Bake_5134621`: **six Scene Services, four Scene Packages and a scenario Web Scene**. This collection did not surface as a useful endpoint in the initial indexed search. Several registry extents span much of central Astana; one narrower extent is 71.433895–71.466912 E, 51.128886–51.145364 N. These extents are search metadata only. The names could refer to proposed development scenarios rather than an accurate existing-city reality mesh; actual geometry could not be inspected. [Reproducible Astana scene/package search](https://www.arcgis.com/sharing/rest/search?f=pjson&q=Astana%20AND%20%28type%3A%22Scene%20Service%22%20OR%20type%3A%22Web%20Scene%22%20OR%20type%3A%22Scene%20Package%22%29&num=100)

All six services share the organization host path `tiles.arcgis.com/tiles/hGOqNu7yXCghNyYS/arcgis/rest/services/`. Their real `/SceneServer/layers/0` responses returned **ArcGIS error 499, Token Required**. Associated service-item metadata returned **403 `SB_0005`, Subscription is disabled**. The scenario's `/data` returned the same disabled-subscription error. [Representative actual layer request](https://tiles.arcgis.com/tiles/hGOqNu7yXCghNyYS/arcgis/rest/services/_1_1_Astana_DIMASH_tower/SceneServer/layers/0?f=pjson), [associated item metadata](https://www.arcgis.com/sharing/rest/content/items/c3fa6223d0ce4d3ea3760264ac2a2622?f=pjson)

The four package items still expose public metadata and sizes, but all four actual `/data` downloads returned **HTTP 403**:

| Package item | Metadata size | Download result |
| --- | ---: | --- |
| `4705853177ff498d9faab58f0401234f` | 198,425,916 bytes | 403 |
| `8f4a6557bea34fa197800621a6a4c88c` | 290,828,319 bytes | 403 |
| `803ce80dec774f698ab10e1485aa09c9` | 279,473,992 bytes | 403 |
| `6d9f8f9fe93646ccb90a66525d430a92` | 147,343,684 bytes | 403 |

All tested public package metadata has null `licenseInfo` and `accessInformation`. No package was downloaded and no mesh was rendered from this collection. These endpoints are an acquisition lead if their owner restores access and confirms the model contents and rights; they are not a working central-city source. [Example package metadata](https://www.arcgis.com/sharing/rest/content/items/4705853177ff498d9faab58f0401234f?f=pjson)

## 3. Other public scenes do not supply the missing mesh

- **KazUAV map for Astana Innovations**, item `b855e71a8d2e4ad387be6053ca3ea28b`: its actual scene JSON contains topographic basemap and terrain references, with no operational reality-mesh layer. The title alone is not evidence of photogrammetric coverage. [Scene JSON](https://www.arcgis.com/sharing/rest/content/items/b855e71a8d2e4ad387be6053ca3ea28b/data?f=pjson)
- **Astana**, item `566c2166c10a45b5b3c67a543abc57c0`: the scene contains a `primer/MapServer` reference at `gis.genplan.kz:6443` plus Esri basemap/terrain. The old map service and its public service directory timed out at 12 seconds each. Even its scene metadata describes a map service, not an I3S reality mesh. [Scene JSON](https://www.arcgis.com/sharing/rest/content/items/566c2166c10a45b5b3c67a543abc57c0/data?f=pjson)
- **Астана**, item `7dbf39bc9f014bf3906c3064c7cdcc11`: uses Esri's global OpenStreetMap 3D buildings, trees and labels. It does not establish accurate detailed Bayterek or alem.ai geometry and does not satisfy the user's rejected-footprint-extrusion criterion. [Scene JSON](https://www.arcgis.com/sharing/rest/content/items/7dbf39bc9f014bf3906c3064c7cdcc11/data?f=pjson)
- A search-indexed ALKÜ Web Scene turned out to contain Turkish university building services. It was rejected as a geographic false positive after fetching the scene's real layer references.

An ArcGIS Online spatial-intersection search returned 3,363 items because global and incorrectly broad registry extents also intersect Astana. Only its first 100 results were inspected; most were worldwide or unrelated layers. This is **not** an exhaustive spatial dataset audit and the result count must not be presented as 3,363 candidate Astana models. Name searches in English, Russian, old and new city names, landmark names and supplier names provide the more relevant evidence here.

## 4. New primary evidence for the acquisition conversation

KazAeroSpace's [documents page](https://kazaerospace.kz/documents) publishes a certificate linked as its Nur-Sultan 3D GIS copyright. The actual PDF is accessible from the company's document host, not just mentioned in a press release. Its text identifies certificate **9118, dated 2 April 2020**, a **computer program** created 1 April 2020, and the GIS's named authors. [Published certificate PDF](https://api.kazaerospace.kz/storage/documents/%D0%A1%D0%B2%D0%B8%D0%B4%D0%B5%D1%82%D0%B5%D0%BB%D1%8C%D1%81%D1%82%D0%B2%D0%BE%20%D0%BD%D0%B0%203D%20%D0%9D%D1%83%D1%80-%D0%A1%D1%83%D0%BB%D1%82%D0%B0%D0%BD_020420.pdf)

This supports contacting the original software supplier, alongside the city's Architecture and Urban Planning Department identified in the supplier's [project description](https://kazaerospace.com/projects/card/9). **It does not identify the aerial data's legal owner, establish an open license, authorize conversion or redistribution, or show that software rights and mesh rights are held by the same party.** The existing [prepared data request](./astana-3d-data-request.md) should still ask explicitly for the actual mesh rights holder and licensed coverage around Bayterek and alem.ai.

The supplier's [current contact page](https://kazaerospace.kz/contacts) publishes `info@kazaerospace.com`, +7 7172 70 64 49 and an Astana office address at Kerey and Zhanibek Khans 5/1. No message was sent. The separate [KASMapping project](https://www.kasmapping.kz/) confirms an active aerial mapping technology effort based at KazAeroSpace; its stated image resolution and positioning capability describe a proposed survey system, not measured accuracy or licensed central-Astana mesh availability.

A procurement-oriented discovery query did not yield a relevant verified contract or tender identifier. Unrelated construction records were discarded. The 2025 Astana Hub CV/AI mapping task is a land-use compliance challenge, not a public city-mesh download or a municipal mesh license.

## Search accounting and confidence

Six successful, distinct Exa queries requested **60 result slots**, returned **60 result blocks**, and yielded **48 unique exact result URLs**. There were **zero schema-failed calls** in this workstream. These are discovery measures, not counts of validated useful sources. The evidence file preserves query text and result URLs separately from the direct API validation.

Confidence is high that the tested municipal endpoint was unavailable during this check and the tested DIMASH endpoints were not anonymously usable: both conclusions come from response bodies. Confidence is high that no alternate municipal service host occurs in the complete current public Scene Service catalog. Confidence is low regarding DIMASH's real mesh coverage, landmark quality and authorship because actual geometry could not be accessed. Public central-city dataset availability elsewhere remains unproven; this follow-up does not claim to have searched every private catalog or commercial supplier.
