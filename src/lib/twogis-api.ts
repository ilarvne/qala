export type TwoGISStatus = "matched" | "ambiguous" | "not_found" | "unavailable" | "key_required";
export type TwoGISContact = { type: string; value: string; url: string | null; comment: string | null };
export type TwoGISCandidate = { provider_id: string; name: string; url: string; lat: number | null; lon: number | null; address: string | null; distance_m: number | null };
export type TwoGISProfile = Omit<TwoGISCandidate, "distance_m"> & {
  provider: "2gis"; rating: number | null; rating_count: number | null; review_count: number | null;
  schedule: Partial<Record<Weekday, { working_hours: { from: string; to: string }[] }>>;
  schedule_comment: string | null; schedule_special: unknown[] | null; contacts: TwoGISContact[];
  rubrics: { id: string; name: string }[]; photo_gallery_url: string | null; review_url: string | null;
  has_photos: boolean | null; route_url: string | null;
};
export type TwoGISResponse = { status: TwoGISStatus; checked_at: string | null; cached: boolean; source: TwoGISProfile | null; candidates: TwoGISCandidate[] };
export const weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;
export type Weekday = typeof weekdays[number];

const object = (value: unknown): Record<string, unknown> | null => value != null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
const text = (value: unknown, limit = 1500) => typeof value === "string" && value.trim() ? value.trim().slice(0, limit) : null;
const number = (value: unknown, min: number, max: number) => typeof value === "number" && Number.isFinite(value) && value >= min && value <= max ? value : null;
const count = (value: unknown) => typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
const time = (value: unknown) => typeof value === "string" && /^(?:[01]\d|2[0-3]):[0-5]\d$|^24:00$/.test(value) ? value : null;

/** Provider links must identify this exact organization; no credentialed URLs. */
export function twoGISLink(value: unknown, providerId: string): string | null {
  if (typeof value !== "string" || !/^\d+$/.test(providerId)) return null;
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" || url.hostname !== "2gis.kz" || url.username || url.password || url.port || url.search || url.hash) return null;
    return new RegExp(`^/astana/firm/${providerId}(?:/tab/(?:photos|reviews))?/?$`).test(url.pathname) ? url.href : null;
  } catch { return null; }
}

function candidate(value: unknown): TwoGISCandidate | null {
  const data = object(value);
  if (!data) return null;
  const providerId = text(data.provider_id, 100), name = text(data.name, 500);
  const url = providerId && twoGISLink(data.url, providerId);
  if (!providerId || !name || !url) return null;
  return { provider_id: providerId, name, url, address: text(data.address), lat: number(data.lat, -90, 90), lon: number(data.lon, -180, 180), distance_m: number(data.distance_m, 0, 1_000_000) };
}

function profile(value: unknown): TwoGISProfile | null {
  const data = object(value), base = candidate(value);
  if (!data || !base || data.provider !== "2gis") return null;
  const schedule: TwoGISProfile["schedule"] = {};
  const rawSchedule = object(data.schedule);
  for (const day of weekdays) {
    const detail = object(rawSchedule?.[day]);
    if (!detail || !Array.isArray(detail.working_hours)) continue;
    schedule[day] = { working_hours: detail.working_hours.flatMap(item => {
      const interval = object(item), from = time(interval?.from), to = time(interval?.to);
      return from && to ? [{ from, to }] : [];
    }).slice(0, 12) };
  }
  const contacts = (Array.isArray(data.contacts) ? data.contacts : []).flatMap(value => {
    const item = object(value), type = text(item?.type, 100), valueText = text(item?.value, 500);
    return type && valueText ? [{ type, value: valueText, url: text(item?.url, 2000), comment: text(item?.comment, 500) }] : [];
  }).slice(0, 20);
  return { ...base, provider: "2gis", rating: number(data.rating, 0, 5), rating_count: count(data.rating_count), review_count: count(data.review_count),
    schedule, schedule_comment: text(data.schedule_comment), schedule_special: Array.isArray(data.schedule_special) ? data.schedule_special
      : object(data.schedule_special) && Object.keys(data.schedule_special as Record<string, unknown>).length ? [data.schedule_special] : null,
    contacts, rubrics: (Array.isArray(data.rubrics) ? data.rubrics : []).flatMap(value => {
      const item = object(value), id = text(item?.id, 100), name = text(item?.name, 250);
      return id && name ? [{ id, name }] : [];
    }).slice(0, 8), photo_gallery_url: twoGISLink(data.photo_gallery_url, base.provider_id), review_url: twoGISLink(data.review_url, base.provider_id),
    has_photos: typeof data.has_photos === "boolean" ? data.has_photos : null,
    // No verified route URL is returned by the current provider contract.
    route_url: twoGISLink(data.route_url, base.provider_id) };
}

export function decodeTwoGISResponse(value: unknown): TwoGISResponse {
  const data = object(value);
  const statuses: TwoGISStatus[] = ["matched", "ambiguous", "not_found", "unavailable", "key_required"];
  if (!data || !statuses.includes(data.status as TwoGISStatus)) throw new Error("Invalid 2GIS source response");
  const source = data.status === "matched" ? profile(data.source) : null;
  if (data.status === "matched" && !source) throw new Error("Invalid 2GIS organization identity");
  return { status: data.status as TwoGISStatus, source, checked_at: text(data.checked_at, 100), cached: data.cached === true,
    candidates: data.status === "ambiguous" && Array.isArray(data.candidates) ? data.candidates.flatMap(value => { const item = candidate(value); return item ? [item] : []; }).slice(0, 10) : [] };
}

/** Only explicit public websites and validated phone/email contact values. */
export function twoGISContactLink(contact: TwoGISContact): string | null {
  if (contact.type === "phone") {
    const value = contact.value.replace(/[\s()−–-]/g, "");
    return /^\+?\d{5,18}$/.test(value) ? `tel:${value}` : null;
  }
  if (contact.type === "email") return /^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i.test(contact.value) ? `mailto:${encodeURIComponent(contact.value).replace("%40", "@")}` : null;
  try {
    const url = new URL(contact.url || contact.value);
    if (!["https:", "http:"].includes(url.protocol) || url.username || url.password || url.port
      || [...url.searchParams.keys()].some(key => /(?:key|token|secret|signature|credential|auth|session)/i.test(key))) return null;
    return url.href;
  } catch { return null; }
}
