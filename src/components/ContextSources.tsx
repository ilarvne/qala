import { ArrowUpRight, CalendarDots, CloudSun } from "@phosphor-icons/react";
import { sourceLink } from "@/lib/place-data";
import type { CityEvent, Language, Recommendation } from "@/types";

const copy = {
  ru: { weather: "Погода в Астане", feels: "ощущается", wind: "ветер", gust: "порывы", rain: "осадки", km: "км/ч", mm: "мм", source: "Прогноз и источник", events: "События", tickets: "Время, площадка и билеты", unavailable: "Прогноз недоступен", outside_forecast: "Дата вне доступного прогноза", outside_city: "Прогноз доступен для Астаны", disabled: "Погода отключена", indoor: "При выборе мест учтена погода", eventNote: "Дата из официального календаря. Время, площадку и наличие билетов проверьте у организатора." },
  en: { weather: "Astana weather", feels: "feels like", wind: "wind", gust: "gusts", rain: "precipitation", km: "km/h", mm: "mm", source: "Forecast and source", events: "Events", tickets: "Time, venue and tickets", unavailable: "Forecast unavailable", outside_forecast: "Date outside forecast range", outside_city: "Forecast covers Astana", disabled: "Weather disabled", indoor: "Weather considered when selecting places", eventNote: "Date from the official calendar. Confirm time, venue and ticket availability with the organizer." },
  kk: { weather: "Астана ауа райы", feels: "сезіледі", wind: "жел", gust: "екпіні", rain: "жауын-шашын", km: "км/сағ", mm: "мм", source: "Болжам және дереккөз", events: "Іс-шаралар", tickets: "Уақыты, орны және билеттер", unavailable: "Болжам қолжетімсіз", outside_forecast: "Күн болжам ауқымынан тыс", outside_city: "Болжам Астанаға арналған", disabled: "Ауа райы өшірілген", indoor: "Орын таңдауда ауа райы ескерілді", eventNote: "Күн ресми күнтізбеден алынған. Уақытын, орнын және билеттерді ұйымдастырушыдан тексеріңіз." },
};
const record = (value: unknown): Record<string, unknown> | undefined => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : undefined;
const number = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? value : undefined;
export function contextDate(value: unknown, language: Language, time = false): string | undefined {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}(?:T.*)?$/.test(value)) return;
  const parsed = new Date(value.length === 10 ? `${value}T12:00:00+05:00` : value);
  if (!Number.isFinite(parsed.getTime())) return;
  return new Intl.DateTimeFormat(language, { timeZone: "Asia/Almaty", day: "numeric", month: "long", ...(time ? { hour: "2-digit", minute: "2-digit" } : {}) }).format(parsed);
}

/** This is evidence in the source disclosure, never a floating forecast badge. */
export function ContextSources({ result, language }: { result: Recommendation; language: Language }) {
  const t = copy[language], weather = record(result.context.weather), effect = record(result.context.weather_effect);
  if (!weather || weather.status === "disabled") return null;
  const available = weather.status === "available", temperature = number(weather.temperature_c);
  const feels = number(weather.apparent_temperature_c), wind = number(weather.wind_kmh), gust = number(weather.gust_kmh), rain = number(weather.precipitation_mm);
  const href = sourceLink(typeof weather.source_url === "string" ? weather.source_url : undefined);
  const date = contextDate(weather.valid_at, language, true);
  const end = contextDate(weather.window_end, language, true), fetched = contextDate(weather.fetched_at, language, true);
  const dates = {ru: {window: "Интервал прогноза", fetched: "Получен"}, en: {window: "Forecast window", fetched: "Retrieved"}, kk: {window: "Болжам аралығы", fetched: "Алынған уақыты"}}[language];
  return <div className="context-source"><h4><CloudSun />{t.weather}</h4>{date && <time>{date}</time>}
    {end && <p>{dates.window}: {date} — {end}</p>}
    {fetched && <p>{dates.fetched}: {fetched}</p>}
    {available ? <dl className="weather-facts">
      {temperature !== undefined && <div><dt>{t.weather}</dt><dd>{Math.round(temperature)}°C</dd></div>}
      {feels !== undefined && <div><dt>{t.feels}</dt><dd>{Math.round(feels)}°C</dd></div>}
      {wind !== undefined && <div><dt>{t.wind}</dt><dd>{Math.round(wind)} {t.km}</dd></div>}
      {gust !== undefined && <div><dt>{t.gust}</dt><dd>{Math.round(gust)} {t.km}</dd></div>}
      {rain !== undefined && <div><dt>{t.rain}</dt><dd>{rain.toLocaleString(language, {maximumFractionDigits: 1})} {t.mm}</dd></div>}
    </dl> : <p>{t[weather.status as "outside_forecast" | "outside_city" | "unavailable"] || t.unavailable}</p>}
    {effect?.applied === true && <p>{t.indoor}</p>}
    {href && <a href={href} target="_blank" rel="noreferrer">{t.source}<ArrowUpRight /></a>}
    {typeof weather.attribution === "string" && <p className="source-attribution">{weather.attribution}</p>}
  </div>;
}

export function OfficialEvents({ events, language }: { events?: CityEvent[]; language: Language }) {
  const t = copy[language];
  const items = events?.filter(event => typeof event.title === "string" && sourceLink(event.url) && contextDate(event.date, language));
  if (!items?.length) return null;
  return <section className="official-events" aria-label={t.events}><h3><CalendarDots />{t.events}</h3><ul>{items.map(event => <li key={event.id}>
    <time dateTime={event.date}>{contextDate(event.date, language)}</time>
    <a href={sourceLink(event.url)} target="_blank" rel="noreferrer"><strong>{event.title}</strong><ArrowUpRight aria-hidden="true" /><span>{t.tickets}</span></a>
  </li>)}</ul><details><summary>Astana Venue Management</summary><p>{t.eventNote}</p></details></section>;
}
