import { useMemo, useState } from "react";
import { ArrowClockwise, ArrowRight, MagnifyingGlass, MapPin } from "@phosphor-icons/react";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { catalogCategories, catalogPlace, type CatalogPlace, type PlaceCatalog } from "@/lib/place-catalog";
import type { Language } from "@/types";

export function PlaceCatalogBrowser({ open, onOpenChange, catalog, status, onRetry, language, center, onSelect }: {
  open: boolean; onOpenChange: (open: boolean) => void; catalog: PlaceCatalog;
  status: "loading" | "ready" | "error"; onRetry: () => void; language: Language;
  center: { lat: number; lon: number }; onSelect: (place: CatalogPlace) => void;
}) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [limit, setLimit] = useState(40);
  const t = language === "ru" ? { title: "Места на карте", search: "Название места", all: "Все категории", category: "Категория", empty: "Места не найдены", more: "Показать ещё", loading: "Загружаем места…", error: "Не удалось загрузить места", retry: "Повторить" }
    : language === "kk" ? { title: "Картадағы орындар", search: "Орынның атауы", all: "Барлық санаттар", category: "Санат", empty: "Орындар табылмады", more: "Тағы көрсету", loading: "Орындар жүктелуде…", error: "Орындар жүктелмеді", retry: "Қайталау" }
    : { title: "Places on the map", search: "Place name", all: "All categories", category: "Category", empty: "No places found", more: "Show more", loading: "Loading places…", error: "Places couldn’t load", retry: "Try again" };
  const results = useMemo(() => {
    const tokens = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    return catalog.features.filter(feature => (!category || feature.properties.category === category) &&
      tokens.every(token => Object.values(feature.properties).join(" ").toLocaleLowerCase().includes(token)))
      .map(feature => catalogPlace(feature, language))
      .sort((a, b) => ((a.lat - center.lat) ** 2 + ((a.lon - center.lon) * .63) ** 2) -
        ((b.lat - center.lat) ** 2 + ((b.lon - center.lon) * .63) ** 2));
  }, [catalog, query, category, language, center.lat, center.lon]);
  const labels = catalogCategories[language];
  return <Sheet open={open} onOpenChange={onOpenChange}><SheetContent className="catalog-browser">
    <SheetHeader><SheetTitle>{t.title}</SheetTitle><SheetDescription className="sr-only">{t.search}</SheetDescription></SheetHeader>
    <div className="catalog-browser-filters"><label><MagnifyingGlass aria-hidden="true" /><input value={query} placeholder={t.search} aria-label={t.search} onChange={event => { setQuery(event.target.value); setLimit(40); }} /></label>
      <select value={category} aria-label={t.category} onChange={event => { setCategory(event.target.value); setLimit(40); }}><option value="">{t.all}</option>{Object.entries(labels).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select></div>
    <div className="catalog-browser-results" aria-busy={status === "loading"}>
      {status === "loading" && <p role="status">{t.loading}</p>}
      {status === "error" && <div role="alert"><p>{t.error}</p><Button variant="outline" onClick={onRetry}><ArrowClockwise />{t.retry}</Button></div>}
      {status === "ready" && !results.length && <p role="status">{t.empty}</p>}
      {status === "ready" && <ul>{results.slice(0, limit).map(place => <li key={place.id}><button onClick={() => { onOpenChange(false); onSelect(place); }}><MapPin aria-hidden="true" /><span><strong>{place.name}</strong><span>{labels[place.category] || place.category}</span></span><ArrowRight aria-hidden="true" /></button></li>)}</ul>}
      {status === "ready" && results.length > limit && <Button variant="outline" className="catalog-browser-more" onClick={() => setLimit(value => value + 40)}>{t.more}</Button>}
    </div>
  </SheetContent></Sheet>;
}
