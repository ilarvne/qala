import { ArrowSquareOut, BookmarkSimple, CaretDown, Clock, Footprints, Globe, MapPin, Phone, Wheelchair } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { PlaceGallery } from "@/components/PlacePhoto";
import { PlaceRating } from "@/components/PlaceRating";
import { TwoGISSource } from "@/components/TwoGISSource";
import { sourceLink } from "@/lib/place-data";
import { placeHours } from "@/lib/place-hours";
import type { PlaceProfileState } from "@/hooks/usePlaceProfiles";
import type { Language, Place } from "@/types";

const words = {
  ru: { map: "На карте", save: "Сохранить", saved: "Сохранено", hours: "Часы работы", unknownHours: "График не указан", visit: "мин на месте", walk: "мин пешком", nearby: "Вы рядом", website: "Сайт", call: "Позвонить", sources: "Источники", idea: "Идея для прогулки", access: "Доступность на коляске", yes: "Доступно", no: "Недоступно", limited: "Ограничена" },
  en: { map: "On map", save: "Save", saved: "Saved", hours: "Opening hours", unknownHours: "Hours not listed", visit: "min here", walk: "min walk", nearby: "You're here", website: "Website", call: "Call", sources: "Sources", idea: "Visit idea", access: "Wheelchair access", yes: "Listed", no: "Not accessible", limited: "Limited" },
  kk: { map: "Картада", save: "Сақтау", saved: "Сақталды", hours: "Жұмыс уақыты", unknownHours: "Жұмыс уақыты көрсетілмеген", visit: "мин осында", walk: "мин жаяу", nearby: "Жақын жердесіз", website: "Сайт", call: "Қоңырау шалу", sources: "Дереккөздер", idea: "Серуен идеясы", access: "Арбаға қолжетімділік", yes: "Қолжетімді", no: "Қолжетімсіз", limited: "Шектеулі" },
};

export function PlaceDetails({ place, language, profile, saved, onMap, onSave, onRefresh, catalog = place.catalog_only === true }: {
  place: Place; language: Language; profile?: PlaceProfileState; saved: boolean;
  onMap: () => void; onSave: () => void; onRefresh: () => void;
  catalog?: boolean;
}) {
  const t = words[language];
  const provider = profile?.status === "ready" && profile.result?.status === "matched" ? profile.result.source : null;
  const address = provider?.address || place.address;
  const website = sourceLink(place.contact?.website);
  const phone = place.contact?.phone?.replace(/[\s()−–-]/g, "");
  const access = place.accessibility?.wheelchair;
  const sources = [place.source, place.hours_source, place.description_source, place.rating_source]
    .filter((source, index, all) => source && sourceLink(source.url) && all.findIndex(other => other?.url === source.url) === index);
  return <div className="place-details">
    <PlaceGallery place={place} language={language} />
    <PlaceRating place={place} language={language} profile={profile} />
    <div className="place-detail-actions"><Button onClick={onMap}><MapPin data-icon="inline-start" />{t.map}</Button><Button variant="outline" aria-pressed={saved} onClick={onSave}><BookmarkSimple data-icon="inline-start" weight={saved ? "fill" : "regular"} />{saved ? t.saved : t.save}</Button>
      {website && <Button variant="outline" asChild><a href={website} target="_blank" rel="noopener noreferrer"><Globe data-icon="inline-start" />{t.website}</a></Button>}
      {phone && /^\+?\d{5,18}$/.test(phone) && <Button variant="outline" asChild><a href={`tel:${phone}`}><Phone data-icon="inline-start" />{t.call}</a></Button>}
    </div>
    {!catalog && <div className="place-detail-times"><span><Footprints aria-hidden="true" />{place.walk_minutes > 0 ? `${place.walk_minutes} ${t.walk}` : t.nearby}</span><span><Clock aria-hidden="true" />{place.visit_minutes} {t.visit}</span></div>}
    {place.action && <p className="place-detail-action">{place.action}</p>}
    <dl className="place-practical">
      {address && <div><dt><MapPin aria-hidden="true" /><span className="sr-only">{language === "ru" ? "Адрес" : language === "kk" ? "Мекенжай" : "Address"}</span></dt><dd>{address}</dd></div>}
      <div><dt><Clock aria-hidden="true" /><span className="sr-only">{t.hours}</span></dt><dd>{placeHours(provider, place.hours, language) || t.unknownHours}</dd></div>
      {access && ["yes", "no", "limited"].includes(access) && <div><dt><Wheelchair aria-hidden="true" /><span className="sr-only">{t.access}</span></dt><dd>{access === "yes" ? t.yes : access === "no" ? t.no : t.limited}</dd></div>}
    </dl>
    <details className="place-sources"><summary>{t.sources}<CaretDown aria-hidden="true" /></summary><div>
      <TwoGISSource poiId={place.id} language={language} profile={profile} onRefresh={onRefresh} />
      {place.description && <p>{place.description}</p>}
      {place.action && <p><strong>{t.idea}:</strong> {place.action}</p>}
      <div className="place-source-links">{sources.map(source => source && <a href={sourceLink(source.url)} key={source.url} target="_blank" rel="noopener noreferrer">{source.name}<ArrowSquareOut aria-hidden="true" /></a>)}</div>
      {place.reviews?.filter(review => review.text).map((review, index) => <blockquote key={review.id || index}><p>{review.text}</p><a href={sourceLink(review.source_url)} target="_blank" rel="noopener noreferrer">{review.author || review.provider}</a></blockquote>)}
    </div></details>
  </div>;
}
