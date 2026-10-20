import { useEffect, useState } from "react";
import { ArrowUpRight, ArrowsClockwise, CaretDown, CircleNotch, PlugsConnected } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { readApiJson } from "@/lib/api";
import { sourceLink } from "@/lib/place-data";
import { contextDate } from "@/components/ContextSources";
import { integrationDescription } from "@/lib/integration-copy";
import type { Language } from "@/types";
type Integration = { id: string; name: string; status: string; configured: boolean; live_verified: boolean; last_checked_at: string | null; source_url: string; detail: string; capabilities: string[] };
const copy = {
  ru: { title: "Источники и сервисы", load: "Проверка сервисов", retry: "Обновить", error: "Не удалось проверить сервисы", source: "Документация", statuses: { active: "Доступен", configured: "Настроен", available: "Доступен", key_required: "Нужен ключ", restricted: "Есть ограничения", unavailable: "Недоступен", disabled: "Отключён", not_integrated: "Не подключён" } },
  en: { title: "Sources and services", load: "Checking services", retry: "Refresh", error: "Could not check services", source: "Documentation", statuses: { active: "Available", configured: "Configured", available: "Available", key_required: "Key required", restricted: "Restricted", unavailable: "Unavailable", disabled: "Disabled", not_integrated: "Not integrated" } },
  kk: { title: "Дереккөздер мен сервистер", load: "Сервистер тексерілуде", retry: "Жаңарту", error: "Сервистер тексерілмеді", source: "Құжаттама", statuses: { active: "Қолжетімді", configured: "Бапталған", available: "Қолжетімді", key_required: "Кілт қажет", restricted: "Шектеулер бар", unavailable: "Қолжетімсіз", disabled: "Өшірілген", not_integrated: "Қосылмаған" } },
};
export function IntegrationsPanel({ language }: { language: Language }) {
  const t = copy[language];
  const verification = { ru: {yes: "Успешный запрос подтверждён", no: "Успешный запрос в текущем процессе не подтверждён", at: "Последняя проверка"}, en: {yes: "Successful request verified", no: "Successful request not verified in this process", at: "Last checked"}, kk: {yes: "Сәтті сұрау расталды", no: "Осы процесте сәтті сұрау расталмады", at: "Соңғы тексеру"} }[language];
  const [revision, refresh] = useState(0), [items, setItems] = useState<Integration[]>([]), [pending, setPending] = useState(true), [failed, setFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setPending(true); setFailed(false);
    void fetch("/api/integrations", {signal: controller.signal}).then(response => readApiJson<{integrations: Integration[]}>(response, t.error)).then(data => {
      if (!Array.isArray(data.integrations)) throw new Error("Invalid service response");
      if (!controller.signal.aborted) setItems(data.integrations.filter(item => typeof item.id === "string" && typeof item.name === "string"));
    }).catch(() => { if (!controller.signal.aborted) setFailed(true); }).finally(() => { if (!controller.signal.aborted) setPending(false); });
    return () => controller.abort();
  }, [revision, t.error]);
  return <section className="settings-section integration-section" aria-busy={pending}><header><h3><PlugsConnected />{t.title}</h3><Button size="icon" variant="ghost" aria-label={t.retry} disabled={pending} onClick={() => refresh(value => value + 1)}>{pending ? <CircleNotch className="spin" /> : <ArrowsClockwise />}</Button></header>
    {failed ? <p role="alert">{t.error}</p> : pending && !items.length ? <p role="status">{t.load}</p> : <div className="integration-list">{items.map(item => <details key={item.id} className="integration"><summary><span>{item.name}</span><span className="integration-state" data-verified={item.live_verified}>{item.status === "active" ? ({ru:"Активен",en:"Active",kk:"Белсенді"})[language] : t.statuses[item.status as keyof typeof t.statuses] || t.statuses.not_integrated}</span><CaretDown className="integration-caret" /></summary><div className="integration-detail"><p>{integrationDescription(item.id, language, item.detail)}</p>{item.configured && <p>{item.live_verified ? verification.yes : verification.no}</p>}{contextDate(item.last_checked_at, language, true) && <p>{verification.at}: {contextDate(item.last_checked_at, language, true)}</p>}{sourceLink(item.source_url) && <a href={sourceLink(item.source_url)} target="_blank" rel="noreferrer">{t.source}<ArrowUpRight /></a>}</div></details>)}</div>}
  </section>;
}
