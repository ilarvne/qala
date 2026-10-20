import { Star } from "@phosphor-icons/react";
import { hasRating, sourceLink } from "@/lib/place-data";
import type { PlaceProfileState } from "@/hooks/usePlaceProfiles";
import type { Language, Place } from "@/types";

/** Keep provider statistics separate from the reusable open-data place. */
export function PlaceRating({ place, language, profile }: { place: Place; language: Language; profile?: PlaceProfileState }) {
  const source = profile?.status === "ready" && profile.result?.status === "matched" ? profile.result.source : null;
  const rating = source?.rating ?? (hasRating(place) ? place.rating : null);
  if (rating == null) return null;
  const count = source?.rating != null ? source.rating_count : place.rating_count;
  const provider = source?.rating != null ? "2GIS" : place.rating_source?.name;
  const url = source?.rating != null ? source.url : sourceLink(place.rating_source?.url);
  const locale = { en: "en-GB", ru: "ru-KZ", kk: "kk-KZ" }[language];
  const label = { en: "Rating", ru: "Оценка", kk: "Баға" }[language];
  return <span className="place-rating" aria-label={`${label}: ${rating} / 5${count != null ? `, ${count}` : ""}${provider ? `, ${provider}` : ""}`}>
    <Star weight="fill" aria-hidden="true" /><strong>{rating.toLocaleString(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</strong>
    {count != null && <span>({new Intl.NumberFormat(locale).format(count)})</span>}
    {provider && (url ? <a href={url} target="_blank" rel="noopener noreferrer">{provider}</a> : <span>{provider}</span>)}
  </span>;
}
