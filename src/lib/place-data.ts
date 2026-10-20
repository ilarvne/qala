import type { Place, PlacePhoto } from "@/types";

/** External data supplies links, never executable navigation schemes. */
export function sourceLink(value?: string | null): string | undefined {
  if (!value) return undefined;
  if (/^\/(?:images|photos)\/[a-zA-Z0-9_./% -]+$/.test(value)) return value;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : undefined;
  } catch { return undefined; }
}

export function placePhoto(place: Place): PlacePhoto | undefined {
  const photo = place.photos?.find((item) => sourceLink(item.thumbnail_url || item.url) && sourceLink(item.source_url));
  return photo;
}

export function hasRating(place: Place): boolean {
  return typeof place.rating === "number" && Number.isFinite(place.rating) && Boolean(sourceLink(place.rating_source?.url));
}
