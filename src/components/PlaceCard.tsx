import { BookmarkSimple, Check, Clock, Coffee, Footprints, MapPin } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { PlacePhoto } from "@/components/PlacePhoto";
import { PlaceRating } from "@/components/PlaceRating";
import { placePhoto, sourceLink } from "@/lib/place-data";
import type { PlaceProfileState } from "@/hooks/usePlaceProfiles";
import type { Place, Language } from "@/types";

export function placeImage(place: Place): { src: string; label: string; illustrative?: boolean } | null {
  const photo = placePhoto(place);
  const src = photo ? sourceLink(photo.thumbnail_url || photo.url) : undefined;
  return src ? { src, label: `${place.name}${photo?.author ? ` · ${photo.author}` : ""}` } : null;
}

export function PlaceCard({ place, index, language, saved, selected, profile, onSave, onEvidence, onSelect }: {
  place: Place; index: number; language: Language; saved: boolean; selected?: boolean;
  profile?: PlaceProfileState;
  onSave: () => void; onEvidence: () => void; onSelect?: () => void;
}) {
  const t = {
    en: { open: "Open place", map: "On map", save: "Save place", unsave: "Remove saved place", walk: "min walk", visit: "min here", nearby: "You're here" },
    ru: { open: "Открыть место", map: "На карте", save: "Сохранить место", unsave: "Удалить из сохранённого", walk: "мин пешком", visit: "мин на месте", nearby: "Вы рядом" },
    kk: { open: "Орынды ашу", map: "Картада", save: "Орынды сақтау", unsave: "Сақталғаннан өшіру", walk: "мин жаяу", visit: "мин осында", nearby: "Жақын жердесіз" },
  }[language];
  return (
    <article className={"place-card" + (selected ? " selected" : "")} data-place-id={place.id}>
      {placePhoto(place) && <button className="place-picture" onClick={onEvidence} aria-label={`${t.open}: ${place.name}`}>
        <PlacePhoto place={place} />
      </button>}
      <div className="place-content">
        <div className="place-card-top"><span className="stop-number">{index+1}</span>
          <button className="place-name" data-testid={"source-button-" + place.id} onClick={onEvidence}><h3>{place.name}</h3></button>
          <Button variant="ghost" size="icon" className="place-save" aria-label={saved ? t.unsave : t.save} aria-pressed={saved} onClick={onSave}><BookmarkSimple weight={saved ? "fill" : "regular"} /></Button></div>
        <PlaceRating place={place} language={language} profile={profile} />
        <div className="place-card-times"><span><Footprints aria-hidden="true" />{place.walk_minutes > 0 ? `${place.walk_minutes} ${t.walk}` : t.nearby}</span><span><Clock aria-hidden="true" />{place.visit_minutes} {t.visit}</span></div>
        <Button variant="ghost" size="sm" className="place-map-action" onClick={onSelect} aria-label={`${t.map}: ${place.name}`}><MapPin data-icon="inline-start" />{t.map}</Button>
      </div>
    </article>
  );
}

export function SavedPlaceRow({ place, onRemove, onEvidence }: { place: Place; onRemove: () => void; onEvidence: () => void }) {
  return <div className="saved-place"><Coffee /><button onClick={onEvidence}><strong>{place.name}</strong><small>{place.category}</small></button><button onClick={onRemove} aria-label={"Remove " + place.name}><Check /></button></div>;
}
