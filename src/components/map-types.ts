import type { Language, Location, Recommendation } from "@/types";
import type { CatalogPlace } from "@/lib/place-catalog";

export interface StreetRoute {
  geometry: { type: "LineString"; coordinates: [number, number][] };
  distance_m: number;
  duration_seconds: number;
  legs: {
    distance_m: number;
    duration_seconds: number;
    steps: {
      instruction: string;
      distance_m: number;
      duration_seconds: number;
      location: [number, number];
      maneuver_type: number | string;
      geometry_start_index?: number;
      geometry_end_index?: number;
    }[];
  }[];
  provider: string;
  attribution: string;
  mode: "walking";
  street_routed: true;
  warnings?: string[];
  limitations?: string;
  language_used?: string;
  language_fallback?: boolean;
  waypoints?: { input: [number, number]; routed: [number, number]; snap_distance_m: number }[];
}

export interface CityMapProps {
  location: Location;
  result: Recommendation | null;
  language: Language;
  onRoute: () => void;
  selectedId?: string;
  onSelectPlace?: (id: string) => void;
  onCatalogSelect?: (place: CatalogPlace) => void;
  catalogSelection?: CatalogPlace;
  navigation?: StreetRoute | null;
  navigating?: boolean;
  userLocation?: { lat: number; lon: number; accuracy?: number; heading?: number };
  insetBottom?: number;
}
