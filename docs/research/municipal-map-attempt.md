# Municipal mesh implementation attempt

Checked 19 October 2026. **Central Astana: failed. Cesium decoding of the existing northern research sample: passed.** These are separate results. The requested municipal map cannot currently replace the app's map, so the user's instruction to use an alternative applies.

## Actual service attempt

Fresh requests reached the [municipal portal](https://gis.esaulet.kz/portal/sharing/rest/portals/self?f=pjson) and [main scene JSON](https://gis.esaulet.kz/portal/sharing/rest/content/items/b535181687714acb87d95950844aed6a/data?f=pjson). The service directory, 2022 and 2024 mesh layer definitions, and both root-node endpoints returned HTTP 200 **with error JSON**, saying no backend server computer could be reached. They did not return I3S layer or node documents. For example:

- [2022 layer](https://gis.esaulet.kz/server/rest/services/Hosted/Sector289_1_8/SceneServer/layers/0?f=pjson) and [root](https://gis.esaulet.kz/server/rest/services/Hosted/Sector289_1_8/SceneServer/layers/0/nodes/root?f=pjson).
- [2024 layer](https://gis.esaulet.kz/server/rest/services/Hosted/Sector_422_1_8/SceneServer/layers/0?f=pjson) and [root](https://gis.esaulet.kz/server/rest/services/Hosted/Sector_422_1_8/SceneServer/layers/0/nodes/root?f=pjson).

An actual browser running **CesiumJS 1.146.0** called `I3SDataProvider.fromUrl` against the municipal 2022 layer. Initialization rejected with `Request has failed.` No municipal layer, root, geometry or texture loaded. The alternate [DIMASH service](https://tiles.arcgis.com/tiles/hGOqNu7yXCghNyYS/arcgis/rest/services/_1_1_Astana_DIMASH_tower/SceneServer/layers/0?f=pjson) still returned ArcGIS error 499, `Token Required`. No authentication bypass was attempted.

Only configuration presence was inspected: no project/environment I3S URL, SLPK path, 3D Tiles URL or Cesium token was configured. Secret values were neither printed nor written to the evidence.

## Local decoder control

The existing loopback-only SLPK bridge at `127.0.0.1:8183` successfully provided original I3S root/node, geometry and JPEG texture bytes from the 21,291,363-byte `Sector1_9_20cm_FT1.slpk`. Actual browser state reported one loaded I3S layer, `tilesLoaded: true`, 93 content-ready tiles, seven draw commands and 1,792 selected triangles. The sampled geometry and texture resource requests returned HTTP 200 with their expected binary/JPEG MIME types. These view-dependent counters establish decoding and drawing, not city coverage or performance.

The rendered screenshot shows a sparse textured ground patch, without verified landmark architecture. The package's declared extent is 71.410160–71.535578 E and 51.206086–51.223936 N: **neither Bayterek nor alem.ai is inside it**. Its actual source is I3S 1.5, horizontal EPSG:4326 and vertical EPSG:5773 (EGM96); the research viewer does not correct EGM96 heights to ellipsoid heights. Its [public item metadata](https://gis.esaulet.kz/portal/sharing/rest/content/items/426defe5ab154d978d3fce97666db526?f=pjson) still has null `licenseInfo`. No new reuse or redistribution permission has been established.

This sample remains private local research and must not be used as the default central-city model. No model was published, no provider account changed and no app source was modified by this attempt.

Exact fresh response bodies, resource URLs, coverage, source hash, configuration-presence checks and browser evidence are in [municipal-map-attempt.json](../../artifacts/municipal-map-attempt.json). The screenshot is retained only in the ignored private research directory.
