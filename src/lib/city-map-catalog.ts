import type { Map as MapLibreMap } from "maplibre-gl";
import { EMPTY_CATALOG, type CatalogPlace } from "@/lib/place-catalog";
import type { Language } from "@/types";

export const CATALOG_SOURCE = "qala-catalog";
export const CATALOG_CLUSTERS = "qala-catalog-clusters";
export const CATALOG_POINTS = "qala-catalog-points";

export function addCatalogLayers(map: MapLibreMap, language: Language) {
  map.addSource(CATALOG_SOURCE, { type: "geojson", data: EMPTY_CATALOG, cluster: true,
    clusterMaxZoom: 16, clusterRadius: 64,
    attribution: 'Places: <a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a> · <a href="https://docs.overturemaps.org/attribution/">Overture Maps</a> · <a href="https://www.wikidata.org/wiki/Wikidata:Licensing">Wikidata</a>',
  });
  map.addLayer({ id: CATALOG_CLUSTERS, type: "circle", source: CATALOG_SOURCE, filter: ["has", "point_count"],
    paint: { "circle-color": "#ffffff", "circle-radius": ["step", ["get", "point_count"], 14, 20, 18, 100, 23], "circle-stroke-width": 1.5, "circle-stroke-color": "#3666f6" } });
  map.addLayer({ id: "qala-catalog-counts", type: "symbol", source: CATALOG_SOURCE, filter: ["has", "point_count"],
    layout: { "text-field": "{point_count_abbreviated}", "text-size": 12, "text-font": ["Noto Sans Regular"], "text-allow-overlap": true }, paint: { "text-color": "#27344a" } });
  map.addLayer({ id: CATALOG_POINTS, type: "circle", source: CATALOG_SOURCE, filter: ["!", ["has", "point_count"]],
    paint: { "circle-color": ["match", ["get", "category"], "utility", "#718096", "transport", "#718096", "#3666f6"],
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 12, 3.5, 17, 6], "circle-stroke-width": 1.5, "circle-stroke-color": "#ffffff" } });
  map.addLayer({ id: "qala-catalog-names", type: "symbol", source: CATALOG_SOURCE, minzoom: 16,
    filter: ["!", ["has", "point_count"]], layout: { "text-field": ["coalesce", ["get", `name_${language}`], ["get", "name"]],
      "text-size": 12, "text-font": ["Noto Sans Regular"], "text-offset": [0, 1.1], "text-anchor": "top", "text-max-width": 13 },
    paint: { "text-color": "#36445b", "text-halo-color": "#ffffff", "text-halo-width": 1.5 } });
  map.addSource("qala-catalog-selected", { type: "geojson", data: EMPTY_CATALOG });
  map.addLayer({ id: "qala-catalog-selected-ring", type: "circle", source: "qala-catalog-selected",
    paint: { "circle-radius": 11, "circle-color": "#3666f6", "circle-stroke-color": "#ffffff", "circle-stroke-width": 3 } });
  map.addLayer({ id: "qala-catalog-selected-name", type: "symbol", source: "qala-catalog-selected",
    layout: { "text-field": ["get", "name"], "text-size": 14, "text-font": ["Noto Sans Regular"], "text-offset": [0, -1.3], "text-anchor": "bottom", "text-allow-overlap": true, "text-max-width": 16 },
    paint: { "text-color": "#27344a", "text-halo-color": "#ffffff", "text-halo-width": 2 } });
}

export function selectedCatalogData(place?: CatalogPlace) {
  return { type: "FeatureCollection" as const, features: place ? [{ type: "Feature" as const,
    properties: { id: place.id, name: place.name }, geometry: { type: "Point" as const, coordinates: [place.lon, place.lat] } }] : [] };
}
