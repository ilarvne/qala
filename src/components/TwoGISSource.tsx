import { useEffect, useId, useState } from "react";
import { ArrowSquareOut, ArrowsClockwise, CaretDown, CircleNotch, Clock, Images, MapPin, NavigationArrow, Star, WarningCircle } from "@phosphor-icons/react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Empty, EmptyDescription, EmptyHeader } from "@/components/ui/empty";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { readApiJson } from "@/lib/api";
import { decodeTwoGISResponse, twoGISContactLink, weekdays, type TwoGISProfile, type TwoGISResponse } from "@/lib/twogis-api";
import type { Language } from "@/types";
import type { PlaceProfileState } from "@/hooks/usePlaceProfiles";
import "./twogis-source.css";

const copy = {
  ru: { loading: "Загрузка 2GIS", refresh: "Обновить данные 2GIS", retry: "Повторить", failed: "Не удалось загрузить 2GIS", timeout: "2GIS не ответил вовремя", notFound: "Совпадение в 2GIS не найдено.", keyRequired: "2GIS не подключён.", ambiguous: "Проверьте адрес в 2GIS", rating: "Оценка", ratings: "Оценок", reviews: "Отзывов", unknown: "Нет данных", schedule: "График работы", contacts: "Контакты", phone: "Телефон", email: "Почта", website: "Сайт", contact: "Контакт", photos: "Фото", reviewLink: "Отзывы", route: "Маршрут", special: "Особый график в 2GIS", meters: "м", kilometers: "км", days: ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"] },
  en: { loading: "Loading 2GIS", refresh: "Refresh 2GIS data", retry: "Retry", failed: "Could not load 2GIS", timeout: "2GIS took too long to respond", notFound: "No matching place found in 2GIS.", keyRequired: "2GIS is not connected.", ambiguous: "Check the address in 2GIS", rating: "Rating", ratings: "Ratings", reviews: "Reviews", unknown: "Not reported", schedule: "Opening hours", contacts: "Contacts", phone: "Phone", email: "Email", website: "Website", contact: "Contact", photos: "Photos", reviewLink: "Reviews", route: "Directions", special: "Special hours in 2GIS", meters: "m", kilometers: "km", days: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] },
  kk: { loading: "2GIS жүктелуде", refresh: "2GIS деректерін жаңарту", retry: "Қайталау", failed: "2GIS жүктелмеді", timeout: "2GIS уақытында жауап бермеді", notFound: "2GIS-тен сәйкес орын табылмады.", keyRequired: "2GIS қосылмаған.", ambiguous: "2GIS-тегі мекенжайды тексеріңіз", rating: "Баға", ratings: "Бағалар", reviews: "Пікірлер", unknown: "Көрсетілмеген", schedule: "Жұмыс уақыты", contacts: "Байланыс", phone: "Телефон", email: "Эл. пошта", website: "Сайт", contact: "Байланыс", photos: "Фото", reviewLink: "Пікірлер", route: "Бағыт", special: "2GIS-тегі арнайы жұмыс уақыты", meters: "м", kilometers: "км", days: ["Дс", "Сс", "Ср", "Бс", "Жм", "Сб", "Жс"] },
};
const locales = { ru: "ru-KZ", en: "en-GB", kk: "kk-KZ" };

function Profile({ source, language }: { source: TwoGISProfile; language: Language }) {
  const t = copy[language], format = new Intl.NumberFormat(locales[language]);
  const scheduleAvailable = weekdays.some(day => source.schedule[day]?.working_hours.length);
  return <div className="twogis-profile">
    <div className="twogis-identity"><h4><a href={source.url} target="_blank" rel="noopener noreferrer">{source.name}<ArrowSquareOut aria-hidden="true" /></a></h4>
      {source.address && <p className="twogis-address"><MapPin aria-hidden="true" />{source.address}</p>}
    </div>
    <dl className="twogis-metrics">
      <div><dt>{t.rating}</dt><dd>{source.rating === null ? <span>{t.unknown}</span> : <><Star weight="fill" aria-hidden="true" />{source.rating.toLocaleString(locales[language], { minimumFractionDigits: 1, maximumFractionDigits: 1 })}<span>/ 5</span></>}</dd></div>
      <div><dt>{t.ratings}</dt><dd>{source.rating_count === null ? <span>{t.unknown}</span> : format.format(source.rating_count)}</dd></div>
      <div><dt>{t.reviews}</dt><dd>{source.review_count === null ? <span>{t.unknown}</span> : format.format(source.review_count)}</dd></div>
    </dl>
    {(scheduleAvailable || source.schedule_comment || source.schedule_special?.length) && <div className="twogis-hours">
      {scheduleAvailable && <details><summary><Clock aria-hidden="true" /><span>{t.schedule}</span><CaretDown className="twogis-caret" aria-hidden="true" /></summary>
        <dl className="twogis-week">{weekdays.map((day, index) => <div key={day}><dt>{t.days[index]}</dt><dd>{source.schedule[day]?.working_hours.length ? source.schedule[day]!.working_hours.map(hours => `${hours.from}–${hours.to}`).join(", ") : t.unknown}</dd></div>)}</dl>
      </details>}
      {source.schedule_comment && <p className="twogis-schedule-comment">{source.schedule_comment}</p>}
      {Boolean(source.schedule_special?.length) && <a href={source.url} target="_blank" rel="noopener noreferrer">{t.special}<ArrowSquareOut aria-hidden="true" /></a>}
    </div>}
    {source.contacts.length > 0 && <details className="twogis-contacts"><summary><span>{t.contacts}</span><CaretDown className="twogis-caret" aria-hidden="true" /></summary>
      <dl>{source.contacts.map((contact, index) => { const href = twoGISContactLink(contact); return <div key={`${contact.type}-${index}`}><dt>{({ phone: t.phone, email: t.email, website: t.website } as Record<string, string>)[contact.type] || t.contact}</dt><dd>{href ? <a href={href} target={href.startsWith("http") ? "_blank" : undefined} rel={href.startsWith("http") ? "noopener noreferrer" : undefined}>{contact.value}</a> : contact.value}{contact.comment && <small>{contact.comment}</small>}</dd></div>; })}</dl>
    </details>}
    <div className="twogis-actions">
      {source.has_photos === true && source.photo_gallery_url && <Button variant="outline" size="sm" asChild><a href={source.photo_gallery_url} target="_blank" rel="noopener noreferrer"><Images data-icon="inline-start" />{t.photos}<ArrowSquareOut data-icon="inline-end" /></a></Button>}
      {source.review_url && <Button variant="outline" size="sm" asChild><a href={source.review_url} target="_blank" rel="noopener noreferrer">{t.reviewLink}<ArrowSquareOut data-icon="inline-end" /></a></Button>}
      {source.route_url && <Button variant="outline" size="sm" asChild><a href={source.route_url} target="_blank" rel="noopener noreferrer"><NavigationArrow data-icon="inline-start" />{t.route}<ArrowSquareOut data-icon="inline-end" /></a></Button>}
    </div>
  </div>;
}

type RequestState = { key: string; result: TwoGISResponse | null; pending: boolean; error: "failed" | "timeout" | null };

/** Mount only after the user opens a place's existing source dialog. */
export function TwoGISSource({ poiId, language, profile, onRefresh }: { poiId: string; language: Language; profile?: PlaceProfileState; onRefresh?: () => void }) {
  const heading = useId(), t = copy[language], key = `${poiId}/${language}`;
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<RequestState>({ key, result: null, pending: true, error: null });
  useEffect(() => {
    if (profile) return;
    const controller = new AbortController();
    let current = true, timedOut = false;
    setState({ key, result: null, pending: true, error: null });
    const timeout = window.setTimeout(() => { timedOut = true; controller.abort(); }, 20_000);
    void fetch(`/api/pois/${encodeURIComponent(poiId)}/sources/2gis?language=${language}`, { signal: controller.signal, cache: "no-store" })
      .then(response => readApiJson<unknown>(response, t.failed)).then(decodeTwoGISResponse)
      .then(result => { if (current && !controller.signal.aborted) setState({ key, result, pending: false, error: null }); })
      .catch(() => { if (current && (!controller.signal.aborted || timedOut)) setState({ key, result: null, pending: false, error: timedOut ? "timeout" : "failed" }); })
      .finally(() => window.clearTimeout(timeout));
    return () => { current = false; window.clearTimeout(timeout); controller.abort(); };
  }, [key, poiId, language, attempt, t.failed, profile]);
  const active = profile ? { key, result: profile.result, pending: profile.status === "loading", error: profile.error } : state.key === key ? state : { key, result: null, pending: true, error: null };
  const refresh = () => onRefresh ? onRefresh() : setAttempt(value => value + 1);
  const result = active.result;
  const unavailable = active.error || (result?.status === "unavailable" ? "failed" : null);
  return <section className="twogis-source" aria-labelledby={heading} aria-busy={active.pending}>
    <Separator />
    <header><h3 id={heading}>2GIS</h3><Button variant="ghost" size="icon" aria-label={t.refresh} disabled={active.pending} onClick={refresh}>
      {active.pending ? <CircleNotch className="spin" data-icon="inline-start" aria-hidden="true" /> : <ArrowsClockwise data-icon="inline-start" aria-hidden="true" />}
    </Button></header>
    {active.pending ? <div className="twogis-loading" role="status"><span className="sr-only">{t.loading}</span><div aria-hidden="true"><Skeleton className="h-4 w-2/3" /><Skeleton className="h-4 w-full" /><Skeleton className="h-8 w-1/2" /></div></div>
      : unavailable ? <Alert><WarningCircle aria-hidden="true" /><AlertTitle>{t[unavailable]}</AlertTitle><AlertDescription><Button variant="outline" size="sm" onClick={refresh}>{t.retry}</Button></AlertDescription></Alert>
      : result?.status === "matched" && result.source ? <Profile source={result.source} language={language} />
      : result?.status === "ambiguous" ? <div className="twogis-ambiguous"><p>{t.ambiguous}</p><ul>{result.candidates.map(candidate => <li key={candidate.provider_id}><a href={candidate.url} target="_blank" rel="noopener noreferrer"><span><strong>{candidate.name}</strong>{candidate.address && <span>{candidate.address}</span>}{candidate.distance_m !== null && <small>{candidate.distance_m < 1000 ? `${Math.round(candidate.distance_m)} ${t.meters}` : `${(candidate.distance_m / 1000).toLocaleString(locales[language], { maximumFractionDigits: 1 })} ${t.kilometers}`}</small>}</span><ArrowSquareOut aria-hidden="true" /></a></li>)}</ul></div>
      : <Empty className="items-start gap-2 p-0 text-left md:p-0"><EmptyHeader className="items-start text-left"><EmptyDescription>{result?.status === "key_required" ? t.keyRequired : t.notFound}</EmptyDescription></EmptyHeader></Empty>}
  </section>;
}
