import { useEffect, useState } from "react";
import { Buildings, CaretLeft, CaretRight, Tree } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { placePhoto, sourceLink } from "@/lib/place-data";
import type { Language, Place, PlacePhoto as PhotoData } from "@/types";

export function PlacePhoto({ place, className = "" }: { place: Place; className?: string }) {
  const photo = placePhoto(place);
  const src = photo ? sourceLink(photo.thumbnail_url || photo.url) : undefined;
  const [failed, setFailed] = useState<string>();
  return src && failed !== src ? <img className={className} src={src} alt={place.name} loading="lazy" decoding="async" referrerPolicy="no-referrer" onLoad={event => { const image = event.currentTarget; image.dataset.orientation = image.naturalHeight > image.naturalWidth ? "portrait" : "landscape"; }} onError={() => setFailed(src)} /> :
    <span className={`place-picture-fallback ${className}`} aria-hidden="true">{/park|garden|playground/.test(place.category) ? <Tree weight="duotone" /> : <Buildings weight="duotone" />}</span>;
}

export function PhotoCredit({ place, selected }: { place: Place; selected?: PhotoData }) {
  const photo = selected ?? placePhoto(place);
  if (!photo) return null;
  return <div className="photo-credit"><a href={sourceLink(photo.source_url)} target="_blank" rel="noreferrer">{photo.author || photo.provider || "Photo source"}</a>{photo.license && <><span aria-hidden="true"> · </span><a href={sourceLink(photo.license_url) || sourceLink(photo.source_url)} target="_blank" rel="noreferrer">{photo.license}</a></>}</div>;
}

export function PlaceGallery({ place, language = "en" }: { place: Place; language?: Language }) {
  const [index, setIndex] = useState(0);
  const [loaded, setLoaded] = useState<string>(), [failed, setFailed] = useState<string>();
  useEffect(() => setIndex(0), [place.id]);
  const photos = place.photos?.filter(photo => sourceLink(photo.url) && sourceLink(photo.source_url)) ?? [];
  const photo = photos[index] ?? placePhoto(place);
  const src = photo && sourceLink(photo.url);
  const labels = {en: ["Previous photo", "Next photo"], ru: ["Предыдущее фото", "Следующее фото"], kk: ["Алдыңғы фото", "Келесі фото"]}[language];
  if (!photo || !src || failed === src) return null;
  return <figure className="place-gallery"><div className="evidence-image"><img key={src} className="gallery-photo" data-loaded={loaded === src} src={src} alt={photo.title || place.name} decoding="async" referrerPolicy="no-referrer" onLoad={() => setLoaded(src)} onError={() => setFailed(src)} /></div><figcaption><PhotoCredit place={place} selected={photo} />{photos.length > 1 && <div className="gallery-controls"><Button variant="ghost" size="icon" aria-label={labels[0]} disabled={index === 0} onClick={() => setIndex(value => value - 1)}><CaretLeft /></Button><span aria-live="polite">{index + 1} / {photos.length}</span><Button variant="ghost" size="icon" aria-label={labels[1]} disabled={index === photos.length - 1} onClick={() => setIndex(value => value + 1)}><CaretRight /></Button></div>}</figcaption></figure>;
}
