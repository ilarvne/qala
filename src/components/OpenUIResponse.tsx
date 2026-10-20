import { Component, createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { action, createLibrary, defineAction, defineComponent, Renderer, useStateField, useTriggerAction } from "@openuidev/react-lang";
import { z } from "zod/v4";
import { ArrowRight, BookmarkSimple, CaretDown, Clock, Footprints, MapPin, SlidersHorizontal, Wheelchair } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PlacePhoto } from "@/components/PlacePhoto";
import { PlaceRating } from "@/components/PlaceRating";
import type { PlaceProfileState } from "@/hooks/usePlaceProfiles";
import { ContextSources, OfficialEvents } from "@/components/ContextSources";
import { hasRating, placePhoto, sourceLink } from "@/lib/place-data";
import type { Language, Place, Recommendation } from "@/types";
import "@/styles/openui.css";

export interface OpenUIConstraints {
  duration?: number; indoor?: boolean; accessible?: boolean; group?: number; airportTransfer?: number | null;
}
interface ResponseContext {
  result: Recommendation; language: Language; savedIds: string[];
  profiles?: Readonly<Record<string, PlaceProfileState>>;
  onSelect: (id: string) => void; onInspect: (place: Place) => void; onSave: (place: Place) => void;
  onFollowUp: (text: string) => void; onRefine: (values: OpenUIConstraints) => void;
}
const Context = createContext<ResponseContext | null>(null);
function useResponse() {
  const context = useContext(Context);
  if (!context) throw new Error("The city response is unavailable.");
  return context;
}
const words = {
  en: { plan: "Your plan", stops: "stops", min: "min", walking: "walking", visit: "visit", sources: "Place details", save: "Save place", saved: "Remove saved place", show: "Show on map", preferences: "Adjust this plan", time: "Time available", group: "People", indoor: "Indoors only", access: "Wheelchair access listed", apply: "Update plan", compare: "Compare places", hours: "Listed hours", rating: "Rating", unknown: "Not listed", facts: "Sources", route: "Estimated walking until street routing finishes", error: "This interactive plan couldn’t load.", retry: "Try again", next: "Refine your plan", photo: "Photo", selected: "Selected", yes: "Listed", no: "Not listed" },
  ru: { plan: "Ваш план", stops: "места", min: "мин", walking: "пешком", visit: "посещение", sources: "Об этом месте", save: "Сохранить место", saved: "Удалить из сохранённых", show: "На карте", preferences: "Изменить план", time: "Свободное время", group: "Человек", indoor: "Только в помещении", access: "Доступность на коляске указана", apply: "Обновить план", compare: "Сравнение мест", hours: "Часы работы", rating: "Рейтинг", unknown: "Не указано", facts: "Источники", route: "Время пешком уточняется по улицам", error: "Не удалось открыть интерактивный план.", retry: "Повторить", next: "Уточнить план", photo: "Фото", selected: "Выбрано", yes: "Указана", no: "Не указана" },
  kk: { plan: "Жоспарыңыз", stops: "орын", min: "мин", walking: "жаяу", visit: "бару", sources: "Орын туралы", save: "Орынды сақтау", saved: "Сақталғаннан өшіру", show: "Картадан көру", preferences: "Жоспарды өзгерту", time: "Бос уақыт", group: "Адам саны", indoor: "Тек ғимарат ішінде", access: "Арбаға қолжетімділік көрсетілген", apply: "Жоспарды жаңарту", compare: "Орындарды салыстыру", hours: "Жұмыс уақыты", rating: "Рейтинг", unknown: "Көрсетілмеген", facts: "Дереккөздер", route: "Жаяу уақыт көше бағытымен нақтыланады", error: "Интерактивті жоспар ашылмады.", retry: "Қайталау", next: "Жоспарды нақтылау", photo: "Фото", selected: "Таңдалды", yes: "Көрсетілген", no: "Көрсетілмеген" },
};

const SelectPlace = defineAction({ name: "SelectPlace", description: "Focus a place from this response on the embedded map.", params: z.object({ id: z.string() }) });
const InspectPlace = defineAction({ name: "InspectPlace", description: "Inspect a sourced place, photos and available reviews.", params: z.object({ id: z.string() }) });
const SavePlace = defineAction({ name: "SavePlace", description: "Toggle a place in the local saved collection.", params: z.object({ id: z.string() }) });
const ApplyPreferences = defineAction({ name: "ApplyPreferences", description: "Apply explicit values from the plan form.", params: z.object({}) });

const TripSummary = defineComponent({
  name: "TripSummary", description: "Summarize the trusted route total; never invent walking times.", props: z.object({}),
  component: () => {
    const { result, language } = useResponse(); const t = words[language];
    return <header className="oui-summary"><h3><MapPin weight="duotone" />{t.plan}</h3><strong className="qa-plan-duration">{result.route.total_minutes} {t.min}</strong><span>{language === "ru" ? `Мест: ${result.recommendations.length}` : `${result.recommendations.length} ${t.stops}`}<span aria-hidden="true"> · </span>{result.route.walk_minutes} {t.min} {t.walking}</span></header>;
  },
});

const PlaceOption = defineComponent({
  name: "PlaceOption", description: "Display one trusted place by its response ID with map, source and save actions.",
  props: z.object({ id: z.string(), select: action(), inspect: action(), save: action() }),
  component: ({ props }) => {
    const { result, language, savedIds, profiles } = useResponse(); const t = words[language];
    const trigger = useTriggerAction();
    const index = result.recommendations.findIndex((place) => place.id === props.id);
    const place = result.recommendations[index];
    if (!place) return null;
    const saved = savedIds.includes(place.id);
    return <li className="oui-place qa-stop" data-openui-place={place.id}>
      <div className="oui-place-heading"><span className="oui-stop-number">{index + 1}</span><button className="oui-place-name qa-stop-name" onClick={() => void trigger(t.sources, undefined, props.inspect)}><span>{place.name}</span></button><Button variant="ghost" size="icon" className="oui-save" aria-label={saved ? t.saved : t.save} aria-pressed={saved} onClick={() => void trigger(t.save, undefined, props.save)}><BookmarkSimple weight={saved ? "fill" : "regular"} /></Button></div>
      {placePhoto(place) && <button className="oui-place-photo" onClick={() => void trigger(t.sources, undefined, props.inspect)} aria-label={`${t.sources}: ${place.name}`}><PlacePhoto place={place} /></button>}
      <PlaceRating place={place} language={language} profile={profiles?.[place.id]} />
      <p className="oui-place-why">{place.why}</p>
      <div className="oui-place-meta"><span><Clock />{place.visit_minutes} {t.min} {t.visit}</span><span><Footprints />{place.walk_minutes} {t.min}</span><Button variant="ghost" size="sm" className="oui-map-action" onClick={() => void trigger(t.show, undefined, props.select)}><MapPin data-icon="inline-start" />{t.show}</Button></div>
    </li>;
  },
});
const Itinerary = defineComponent({ name: "Itinerary", description: "An ordered itinerary of one to three sourced places.", props: z.object({ places: z.array(PlaceOption.ref).max(3) }), component: ({ props, renderNode }) => <ol className="oui-itinerary">{renderNode(props.places)}</ol> });

const Comparison = defineComponent({
  name: "Comparison", description: "Compare only existing response places using source facts and routed times.", props: z.object({ ids: z.array(z.string()).min(1).max(3) }),
  component: ({ props }) => {
    const { result, language, onSelect, onInspect, profiles } = useResponse(); const t = words[language];
    const places = props.ids.map((id) => result.recommendations.find((place) => place.id === id)).filter((place): place is Place => Boolean(place));
    const ratingFor = (place: Place) => {
      const state = profiles?.[place.id];
      const source = state?.status === "ready" && state.result?.status === "matched" ? state.result.source : null;
      return source?.rating != null ? { value: source.rating, provider: "2GIS" } : hasRating(place) ? { value: place.rating!, provider: place.rating_source?.name } : null;
    };
    const access = (place: Place) => { const value = place.accessibility?.wheelchair; return value === "yes" ? ({en:"Yes",ru:"Да",kk:"Иә"}[language]) : value === "no" ? ({en:"No",ru:"Нет",kk:"Жоқ"}[language]) : value === "limited" ? ({en:"Limited",ru:"Ограничен",kk:"Шектеулі"}[language]) : t.unknown; };
    return <div className="oui-comparison" role="region" aria-label={t.compare} tabIndex={0}><table><caption>{t.compare}</caption><thead><tr><th scope="col" className="sr-only">{t.facts}</th>{places.map((place) => <th scope="col" key={place.id}><button title={place.name} onClick={() => onSelect(place.id)}>{place.name}</button></th>)}</tr></thead><tbody>
      <tr><th scope="row">{t.walking}</th>{places.map((place) => <td key={place.id}>{place.walk_minutes} {t.min}</td>)}</tr>
      <tr><th scope="row">{t.visit}</th>{places.map((place) => <td key={place.id}>{place.visit_minutes} {t.min}</td>)}</tr>
      <tr><th scope="row">{t.hours}</th>{places.map((place) => <td key={place.id}>{place.hours || t.unknown}</td>)}</tr>
      {(result.conversation?.accessible || places.some(place => /^(yes|no|limited)$/.test(place.accessibility?.wheelchair || ""))) && <tr><th scope="row" aria-label={t.access}>{({en:"Access",ru:"Доступ",kk:"Қолжетімділік"}[language])}</th>{places.map((place) => <td key={place.id}>{access(place)}</td>)}</tr>}
      {places.some(place => ratingFor(place)) && <tr><th scope="row">{t.rating}</th>{places.map((place) => { const rating = ratingFor(place); return <td key={place.id} title={rating?.provider}>{rating ? <>{rating.value.toLocaleString(language === "kk" ? "kk-KZ" : language === "ru" ? "ru-RU" : "en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}{rating.provider && <span className="comparison-provider">{rating.provider}</span>}</> : t.unknown}</td>; })}</tr>}
      <tr><th scope="row" className="sr-only">{t.sources}</th>{places.map((place) => <td key={place.id}><Button variant="outline" size="sm" onClick={() => onInspect(place)}>{t.sources}</Button></td>)}</tr>
    </tbody></table></div>;
  },
});

const PlanControls = defineComponent({
  name: "PlanControls", description: "An explicit editable time, group and accessibility form.", props: z.object({ submit: action() }),
  component: ({ props }) => {
    const { result, language } = useResponse(); const t = words[language]; const trigger = useTriggerAction();
    const conversation = result.conversation;
    const duration = useStateField("duration_minutes", conversation?.duration_minutes ?? result.context.duration_minutes ?? 60);
    const group = useStateField("group_size", conversation?.group_size ?? 1);
    const indoor = useStateField("indoor", conversation?.indoor ?? false);
    const accessible = useStateField("accessible", conversation?.accessible ?? false);
    const [open, setOpen] = useState(false);
    return <details className="oui-controls" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}><summary><SlidersHorizontal />{t.preferences}<CaretDown className="oui-caret" /></summary><form onSubmit={(event) => { event.preventDefault(); void trigger(t.apply, undefined, props.submit); }}>
      <div className="oui-field-row"><label><span>{t.time}</span><Select value={String(duration.value)} onValueChange={(value) => duration.setValue(Number(value))}><SelectTrigger aria-label={t.time}><SelectValue /></SelectTrigger><SelectContent><SelectGroup>{[...new Set([15,30,45,60,90,120,180,Number(duration.value)])].sort((a,b) => a-b).map((value) => <SelectItem value={String(value)} key={value}>{value} {t.min}</SelectItem>)}</SelectGroup></SelectContent></Select></label><label><span>{t.group}</span><Select value={String(group.value)} onValueChange={(value) => group.setValue(Number(value))}><SelectTrigger aria-label={t.group}><SelectValue /></SelectTrigger><SelectContent><SelectGroup>{[...new Set([1,2,3,4,5,Number(group.value)])].sort((a,b) => a-b).map((value) => <SelectItem key={value} value={String(value)}>{value}</SelectItem>)}</SelectGroup></SelectContent></Select></label></div>
      <label className="oui-check"><input type="checkbox" checked={Boolean(indoor.value)} onChange={(event) => indoor.setValue(event.target.checked)} /><span>{t.indoor}</span></label>
      <label className="oui-check"><input type="checkbox" checked={Boolean(accessible.value)} onChange={(event) => accessible.setValue(event.target.checked)} /><Wheelchair /><span>{t.access}</span></label>
      <Button type="submit" className="oui-apply">{t.apply}<ArrowRight data-icon="inline-end" /></Button>
    </form></details>;
  },
});

const Clarifications = defineComponent({
  name: "Clarifications", description: "Ask only the missing information identified by the planner.", props: z.object({}),
  component: () => {
    const { result, onRefine, onFollowUp } = useResponse();
    return <div className="oui-questions">{result.clarifications?.map((question) => <fieldset key={question.field}><legend>{question.message}</legend><div>{question.options.map((option) => <Button variant="outline" size="sm" key={String(option.value)} onClick={() => {
      if (question.field === "airport_transfer_minutes" && typeof option.value === "number") onRefine({ airportTransfer: option.value });
      else if (question.field === "duration_minutes" && typeof option.value === "number") onRefine({ duration: option.value });
      else if (question.field === "indoor" && typeof option.value === "boolean") onRefine({ indoor: option.value });
      else if (question.field === "accessible" && typeof option.value === "boolean") onRefine({ accessible: option.value });
      else onFollowUp(option.label);
    }}>{option.label}</Button>)}</div></fieldset>)}</div>;
  },
});
const FollowUps = defineComponent({
  name: "FollowUps", description: "Contextual next actions from the grounded planner.", props: z.object({}),
  component: () => {
    const { result, language } = useResponse(); const trigger = useTriggerAction();
    return <div className="oui-followups" role="group" aria-label={words[language].next}>{result.followups?.slice(0, 4).map((text) => <Button variant="outline" key={text} onClick={() => void trigger(text)}>{text}<ArrowRight data-icon="inline-end" /></Button>)}</div>;
  },
});
const CityResponse = defineComponent({
  name: "CityResponse", description: "A bounded, source-grounded interactive city answer.",
  props: z.object({ children: z.array(z.union([TripSummary.ref, Itinerary.ref, Comparison.ref, PlanControls.ref, Clarifications.ref, FollowUps.ref])) }),
  component: ({ props, renderNode }) => {
    const { result, language } = useResponse(); const t = words[language];
    const sources = result.recommendations.flatMap((place) => [place.source, place.hours_source, place.description_source]).filter((source, index, all) => source && sourceLink(source.url) && all.findIndex((other) => other?.url === source.url) === index);
    const missing = Array.isArray(result.context.missing_data) ? result.context.missing_data.filter((item): item is string => typeof item === "string") : [];
    return <section className="qa-plan oui-response" data-openui-layout={result.openui?.layout} aria-label={t.plan}><OfficialEvents events={result.events} language={language} />{renderNode(props.children)}{(sources.length > 0 || result.context.weather != null) && <details className="oui-evidence"><summary>{t.facts}<CaretDown className="oui-caret" /></summary>{result.recommendations.length > 0 && result.route.estimated && <p>{t.route}</p>}<ContextSources result={result} language={language} />{missing.map((item, index) => <p key={index}>{item}</p>)}{sources.map((source) => source && <a href={sourceLink(source.url)} key={source.url} target="_blank" rel="noreferrer">{source.name}</a>)}</details>}</section>;
  },
});

export const cityResponseLibrary = createLibrary({ root: "CityResponse", components: [CityResponse, TripSummary, PlaceOption, Itinerary, Comparison, PlanControls, Clarifications, FollowUps], actions: [SelectPlace, InspectPlace, SavePlace, ApplyPreferences] });

class ResponseBoundary extends Component<{ children: ReactNode; fallback: ReactNode }, { failed: boolean }> {
  state = { failed: false }; static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? this.props.fallback : this.props.children; }
}

export function OpenUIResponse(props: ResponseContext) {
  const [invalid, setInvalid] = useState(false);
  const { result, language } = props; const wire = result.openui;
  useEffect(() => setInvalid(false), [wire?.document]);
  const t = words[language];
  const fallback = <div className="oui-recovery" role="alert"><p>{t.error}</p><Button variant="outline" onClick={() => props.onFollowUp(result.followups?.[0] || (language === "en" ? "Plan a walk nearby" : language === "ru" ? "Прогулка рядом" : "Жақын жерде серуен"))}>{t.retry}</Button></div>;
  if (!wire || wire.format !== "openui-lang" || wire.version !== 1 || wire.document.length > 16000 || /\b(?:Query|Mutation)\s*\(/.test(wire.document)) return null;
  return <Context.Provider value={props}><ResponseBoundary key={wire.document} fallback={fallback}>{invalid ? fallback : <Renderer library={cityResponseLibrary} response={wire.document} isStreaming={false} onError={(errors) => { if (errors.length) setInvalid(true); }} onAction={(event) => {
    if (event.type === "continue_conversation") { const text = event.humanFriendlyMessage?.trim(); if (text && text.length <= 3000) props.onFollowUp(text); return; }
    if (event.type === "ApplyPreferences") {
      const fields = event.formState ?? {}; const conversation = result.conversation;
      const value = (key: string, fallback: unknown) => { const raw: unknown = fields[key]; return raw && typeof raw === "object" && "value" in raw ? raw.value : raw ?? fallback; };
      const duration = Number(value("duration_minutes", conversation?.duration_minutes ?? 60));
      const group = Number(value("group_size", conversation?.group_size ?? 1));
      if (!Number.isFinite(duration) || !Number.isFinite(group)) return;
      props.onRefine({ duration: Math.max(10, Math.min(480, duration)), group: Math.max(1, Math.min(20, group)), indoor: Boolean(value("indoor", conversation?.indoor)), accessible: Boolean(value("accessible", conversation?.accessible)) }); return;
    }
    if (event.type === "SelectPlace" || event.type === "InspectPlace" || event.type === "SavePlace") {
      const place = result.recommendations.find((item) => item.id === event.params.id);
      if (!place) return;
      if (event.type === "SelectPlace") props.onSelect(place.id);
      if (event.type === "InspectPlace") props.onInspect(place);
      if (event.type === "SavePlace") props.onSave(place);
    }
  }} />}</ResponseBoundary></Context.Provider>;
}
