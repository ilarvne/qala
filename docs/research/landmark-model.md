# Superseded Bayterek model experiment

This records an intermediate procedural model experiment, removed after the user
requested accurate provider-supplied 3D coverage for the whole map. The current
implementation uses 2GIS when an authorized key is configured and a flat
OpenFreeMap fallback otherwise. See the [provider decision](astana-provider-coverage.md).
The descriptions below explain the discarded experiment, not shipped behavior.

## Primary references

- [Astana Venue Management, the monument operator](https://a-vm.kz/en/objects/bayterek/), checked 2026-10-19: overall structure height **105 m**, sphere diameter **22 m**, and the Ayaly Alaqan composition at **97 m**.
- [Official Visit Astana](https://visitastana.kz/en/about-city/what-to-see/baiterek-the-main-symbol-of-astana/): golden glass sphere, metal tower body, viewing platform at **93 m**, and upper handprint level at **97 m**. Its introductory 97 m height is distinct from the operator's specific overall 105 m measurement.
- [Operator exterior photograph](https://a-vm.kz/wp-content/uploads/2024/04/object-img-1.jpg): visual reference for the narrow elevator core, open white crossing lattice, outward flaring crown and sphere glazing seams. The photograph is a research reference and is not distributed as a model texture or other product asset.

## Modeling assumptions

The sphere has a real-scale 11 m radius and is centered at an inferred 94 m, giving a 105 m sphere top. That center height is a modeling inference, not a separately published measurement. Lattice spacing, shaft radius, crown flare, seam counts and materials are simplified interpretations of the photograph, not engineering drawings. The coordinate comes from the existing Bayterek POI: **51.1282882, 71.4304546**.

The previous generic extrusion stretched two polygon footprints into tall tubes. A read-only query against the actual OpenFreeMap/OpenMapTiles building source at the POI returned these feature IDs:

| Feature ID | Recorded extrusion | Replacement |
| --- | --- | --- |
| `2304016452` | Height 99 m, base 0 m; star shaped shaft footprint | Procedural shaft and crown |
| `2304016442` | Height 110 m, base 98 m; circular sphere footprint | Actual spherical geometry |

Only those two IDs are excluded from the map's generic extrusion layer. Their flat footprints remain available in 2D. All `fill-extrusion` layers are hidden when pitch is at or below 1°, and their prior visibility is restored in 3D. The custom model independently stops drawing in 2D.

## Rendering

`src/lib/bayterek-model.ts` creates the geometry locally, with no model-server or texture dependency. It is lazy loaded after the map style. Rib geometries are merged into a single mesh, and the static model requests no perpetual render loop. Its custom MapLibre layer uses the shared WebGL2 context, meter-scaled Mercator coordinates and `defaultProjectionData.mainMatrix`; it disposes all geometries, materials and renderer resources on layer removal without destroying MapLibre's shared context.

Technical reference: [MapLibre custom-layer API](https://maplibre.org/maplibre-gl-js/docs/API/interfaces/CustomLayerInterface/) and the installed MapLibre GL JS 6.15.0 `CustomRenderMethodInput` type documentation.
