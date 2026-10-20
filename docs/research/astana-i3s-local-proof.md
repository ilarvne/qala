# Local municipal SLPK compatibility proof

19 October 2026. A bounded local experiment successfully rendered actual geometry and texture bytes from the privately downloaded `Sector1_9_20cm_FT1.slpk` using **CesiumJS 1.146.0**, without an API key. This establishes that this particular older package can be decoded and drawn by this version of Cesium. It does not establish supported compatibility for every I3S 1.5 package, full-city coverage, landmark accuracy, data currency, production performance or redistribution permission.

The package identifies itself as `IntegratedMesh`, `meshpyramids`, I3S 1.5, generated with ContextCapture. Its CRS metadata is EPSG:4326 horizontally and EPSG:5773 (EGM96) vertically. Its declared extent is approximately 71.41016–71.53558° E and 51.20609–51.22394° N, in northern Astana. This area excludes Bayterek, Khan Shatyr and alem.ai. Empty `copyrightText` and `Extract` in package capabilities are not an open licence.

The generic [local preview script](../../scripts/research_mesh_preview.py) opens a supplied SLPK ZIP and maps standard I3S resource URLs to its members, including archives with backslash filenames. It decompresses `.gz` resources and serves original node, geometry, feature and JPEG texture bytes. It binds only `127.0.0.1:8183`; it does not upload the package. Cesium's scripts and workers load from the pinned unpkg distribution. No application dependencies or existing application source were changed.

The viewer uses an ellipsoid terrain provider, hides the globe and requests no satellite basemap or external terrain. **No EGM96-to-ellipsoid vertical correction was applied.** Its purpose is decoder and rendering compatibility, not survey alignment. Camera targets come from package bounding spheres; no geometry was fabricated or patched.

An isolated `agent-browser` session, `mesh-research`, inspected the live viewer. Final captured browser state reported:

| Check | Observed result |
| --- | --- |
| Cesium version | 1.146.0 |
| Loaded I3S layers | 1 |
| Content-ready tiles | 131 |
| All tiles required by current view loaded | true |
| Draw commands | 7 |
| Selected triangles | 1,792 |
| Geometry bytes currently accounted | 847,860 |
| Texture bytes currently accounted | 9,268,201 |
| Captured JavaScript/render errors | none |

These are view-dependent internal renderer counters, not a benchmark or total package complexity. Server requests for metadata, geometry and textures returned 200. A favicon request returned an unrelated 404. The initial package is about 21.3 MB on disk; neither that size nor these counters predict full-city performance.

Private screenshots show genuine textured ground patches from the sample. They do **not** show verified landmark buildings or demonstrate a complete city. Changing the camera to an overview showed separated patches. This warrants further inspection of the municipal dataset's useful coverage before any integration claim.

Screenshots, browser evidence JSON and the source SLPK remain under the ignored `artifacts/private/research/astana-3d/` directory. None were published or added as distributable application assets. The latest evidence JSON is `local-i3s-browser-evidence.json`; the lit view is `local-i3s-lighted-cesium-1.146.png`.

To reproduce locally with an authorized copy:

```sh
python scripts/research_mesh_preview.py /absolute/path/to/package.slpk
```

Then open `http://127.0.0.1:8183/`. The server and package must remain local until reuse rights are established. Production work would additionally need verified coverage and dates, datum correction, source attribution, performance checks and validation that all existing map features survive.
