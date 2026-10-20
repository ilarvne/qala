import type { Language, Place } from "@/types";

export interface CatalogPlace {
  id: string; name: string; category: string; lat: number; lon: number;
}
export interface CatalogFeature {
  type: "Feature"; id: string;
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: { id: string; name: string; category: string; name_en?: string; name_ru?: string; name_kk?: string };
}
export interface PlaceCatalog { type: "FeatureCollection"; features: CatalogFeature[] }
export const EMPTY_CATALOG: PlaceCatalog = { type: "FeatureCollection", features: [] };

export function catalogPlace(feature: CatalogFeature, language: Language): CatalogPlace {
  return { id: feature.properties.id, name: feature.properties[`name_${language}`] || feature.properties.name,
    category: feature.properties.category, lon: feature.geometry.coordinates[0], lat: feature.geometry.coordinates[1] };
}

/** Raw source records are not itineraries: no walking time or visit is inferred. */
export function catalogDetail(poi: Record<string, unknown>, language: Language): Place {
  const names = poi.names as Partial<Record<Language, string>> | undefined;
  return { ...poi, catalog_only: true, name: names?.[language] || String(poi.name), why: "", action: "",
    visit_minutes: 0, walk_minutes: 0, distance_m: 0, leg_distance_m: 0,
    hours_status: "unknown", confidence: "source-backed", description: poi.description || "",
    tags: poi.tags || [], hours: poi.hours || null,
  } as Place;
}

export const catalogCategories: Record<Language, Record<string, string>> = {
  en: { cafe: "Coffee", dining: "Food", park: "Parks", culture: "Culture", museum: "Museums", shopping: "Shops", playground: "Playgrounds", sport: "Sports", nightlife: "Nightlife", accommodation: "Hotels", transport: "Transport", utility: "Services", viewpoint: "Viewpoints" },
  ru: { cafe: "Кофе", dining: "Еда", park: "Парки", culture: "Культура", museum: "Музеи", shopping: "Магазины", playground: "Детские площадки", sport: "Спорт", nightlife: "Бары и клубы", accommodation: "Гостиницы", transport: "Транспорт", utility: "Услуги", viewpoint: "Смотровые площадки" },
  kk: { cafe: "Кофе", dining: "Тамақ", park: "Саябақтар", culture: "Мәдениет", museum: "Мұражайлар", shopping: "Дүкендер", playground: "Ойын алаңдары", sport: "Спорт", nightlife: "Барлар мен клубтар", accommodation: "Қонақүйлер", transport: "Көлік", utility: "Қызметтер", viewpoint: "Көрініс алаңдары" },
};
