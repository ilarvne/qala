import type { ExpressionSpecification, FillExtrusionLayerSpecification, Map as MapLibreMap } from "maplibre-gl";
import type { Language } from "@/types";

const BUILDING_LAYER = "qala-buildings-3d";

// The tile schema supplies metres. Defend against missing, negative and
// inconsistent values without inventing heights for individual landmarks.
const height: ExpressionSpecification = ["max", 0, ["to-number", ["get", "render_height"], 0]];
const base: ExpressionSpecification = [
  "min", height, ["max", 0, ["to-number", ["get", "render_min_height"], 0]],
];

/** Localize the verified street-name fields without stacking two alphabets. */
export function setCityMapLanguage(map: MapLibreMap, language: Language) {
  const field: ExpressionSpecification = language === "en"
    ? ["coalesce", ["get", "name:en"], ["get", "name_en"], ["get", "name"]]
    : ["coalesce", ["get", `name:${language}`], ["get", "name"]];
  for (const layer of map.getStyle().layers ?? []) {
    // The same source layer also contains road-number shields, whose `ref`
    // text must remain a road number rather than becoming a street name.
    if (layer.type === "symbol" && layer["source-layer"] === "transportation_name" && layer.id.startsWith("highway-name-")) {
      map.setLayoutProperty(layer.id, "text-field", field);
    }
  }
}

/** True 2D removes every raised layer; camera changes belong to the renderer. */
export function setCityMapDepth(map: MapLibreMap, depth: boolean) {
  for (const layer of map.getStyle().layers ?? []) {
    if (layer.type === "fill-extrusion") {
      map.setLayoutProperty(layer.id, "visibility", depth ? "visible" : "none");
    }
  }
}

/** Prepare the existing Positron style once, after its load event. */
export function prepareCityStyle(map: MapLibreMap, language: Language, depth: boolean) {
  if (!map.getSource("openmaptiles")) throw new Error("The city building source is unavailable.");
  const layers = map.getStyle().layers ?? [];

  // City-wide names become oversized obstacles at the walking scale.
  for (const layer of layers) {
    if (layer.type === "symbol" && /^label_(city(?:_capital)?|country_[123])$/.test(layer.id)) {
      map.setLayerZoomRange(layer.id, layer.minzoom ?? 0, Math.min(layer.maxzoom ?? 24, 13));
    }
  }
  if (map.getLayer("building")) {
    map.setPaintProperty("building", "fill-color", "#e1e6eb");
    map.setPaintProperty("building", "fill-outline-color", "#cfd7df");
  }
  map.setLight({ anchor: "viewport", position: [1.5, 210, 45], color: "#ffffff", intensity: 0.32 });

  if (!map.getLayer(BUILDING_LAYER)) {
    const beforeLabels = layers.find((layer) => layer.type === "symbol" && layer.layout?.["text-field"])?.id;
    const buildings: FillExtrusionLayerSpecification = {
      id: BUILDING_LAYER,
      type: "fill-extrusion",
      source: "openmaptiles",
      "source-layer": "building",
      minzoom: 13.5,
      filter: ["!=", ["get", "hide_3d"], true],
      paint: {
        "fill-extrusion-color": ["interpolate", ["linear"], height, 0, "#dde5ed", 90, "#c7d3e2", 200, "#b8c7d9"],
        "fill-extrusion-height": ["interpolate", ["linear"], ["zoom"], 13.5, 0, 14.5, height],
        "fill-extrusion-base": ["interpolate", ["linear"], ["zoom"], 13.5, 0, 14.5, base],
        "fill-extrusion-opacity": 1,
        "fill-extrusion-vertical-gradient": true,
      },
    };
    map.addLayer(buildings, beforeLabels);
  }
  setCityMapLanguage(map, language);
  setCityMapDepth(map, depth);
}
