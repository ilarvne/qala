import { weekdays, type TwoGISProfile } from "@/lib/twogis-api";
import type { Language } from "@/types";

/** Group only reported weekdays; an absent day never becomes a closure claim. */
export function placeHours(source: TwoGISProfile | null, fallback: string | null, language: Language): string | null {
  if (!source) return fallback;
  const labels = { ru: ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"], en: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], kk: ["Дс", "Сс", "Ср", "Бс", "Жм", "Сб", "Жс"] }[language];
  const groups: { days: number[]; hours: string }[] = [];
  for (const [index, day] of weekdays.entries()) {
    const hours = source.schedule[day]?.working_hours.map(interval => `${interval.from}–${interval.to}`).join(", ");
    if (!hours) continue;
    const last = groups.at(-1);
    if (last && last.hours === hours && last.days.at(-1) === index - 1) last.days.push(index);
    else groups.push({ days: [index], hours });
  }
  return groups.length ? groups.map(group => `${group.days.length === 7 ? ({ ru: "Ежедневно", en: "Daily", kk: "Күн сайын" })[language] : group.days.length > 1 ? `${labels[group.days[0]]}–${labels[group.days.at(-1)!]}` : labels[group.days[0]]} ${group.hours}`).join("; ") : fallback;
}
