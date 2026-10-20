export type Language = "en" | "ru" | "kk";
export interface Location {
  lat: number;
  lon: number;
  label: string;
}
export interface SourceEvidence { name: string; url: string; collected_at?: string }
export interface PlacePhoto {
  url: string; thumbnail_url?: string; source_url: string; title?: string;
  author?: string; license?: string; license_url?: string; attribution?: string;
  provider?: string; observed_at?: string;
}
export interface PlaceReview {
  id?: string; text?: string | null; author?: string; rating?: number; published_at?: string;
  source_url: string; provider: string;
  license?: string; license_url?: string;
  original_rating?: number; original_scale?: number;
}
export interface ConversationContext {
  interests: string[]; excluded_ids: string[]; last_recommendation_ids: string[];
  excluded_categories: string[]; duration_minutes?: number | null;
  accessible?: boolean | null; indoor?: boolean | null; group_size?: number | null;
  airport: boolean; airport_transfer_minutes?: number | null; max_walk_minutes?: number | null;
  event_date?: string | null; outdoor_preference?: boolean | null;
}
export interface Clarification {
  field: string; message: string; options: { label: string; value: string | number | boolean }[];
}
export interface OpenUIDocument {
  version: 1; format: "openui-lang"; document: string;
  layout: "itinerary" | "comparison" | "clarification";
}
export interface Place {
  catalog_only?: boolean;
  id: string;
  name: string;
  lat: number;
  lon: number;
  category: string;
  description: string;
  why: string;
  action: string;
  visit_minutes: number;
  distance_m: number;
  leg_distance_m: number;
  walk_minutes: number;
  hours_status: string;
  hours: string | null;
  confidence: string;
  source: SourceEvidence;
  description_source?: { name: string; url: string };
  hours_source?: { name: string; url: string };
  tags: string[];
  image?: string | null;
  photos?: PlacePhoto[];
  rating?: number | null;
  rating_count?: number | null;
  rating_source?: SourceEvidence | null;
  reviews?: PlaceReview[];
  review_count?: number | null;
  contact?: { phone?: string | null; website?: string | null; email?: string | null };
  address?: string | null;
  amenities?: Record<string, string | null>;
  accessibility?: Record<string, string | null>;
  poi_type?: string;
}
export interface Recommendation {
  message: string;
  recommendations: Place[];
  route: {
    total_minutes: number;
    walk_minutes: number;
    distance_m: number;
    coordinates: [number, number][];
    warning?: string;
    mode?: string;
    estimated?: boolean;
  };
  context: Record<string, unknown>;
  events?: CityEvent[];
  trace: unknown;
  mode: string;
  conversation?: ConversationContext;
  followups?: string[];
  clarifications?: Clarification[];
  openui?: OpenUIDocument;
  retrieval?: {
    corpus_count: number; eligible_count: number; radius_m: number; returned_count: number;
    excluded_counts: Record<string, number>; method: string; embedding_mode: string;
  };
}
export interface CityEvent {
  id: string; title: string; url: string; date: string;
  start_time: string | null; date_precision: "day"; venue: string | null;
  poi_id: string | null; availability: "unverified";
}
export interface Scenario {
  id: string;
  icon: "walk" | "coffee" | "kids" | "flight" | "night";
  minutes: number;
  location: Location;
  message: Record<Language, string>;
  labels: Record<Language, string>;
}
export type Panel = "saved" | "memory" | "settings" | "route" | null;
