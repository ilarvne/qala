import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight, ArrowSquareOut, BookmarkSimple, CaretLeft, CaretRight, ChatCircleDots,
  CalendarDots, Check, CircleNotch, Clock, Coffee, Compass, DownloadSimple, GlobeHemisphereWest,
  Info, MagnifyingGlass, MapPin, MapTrifold, Microphone, NavigationArrow,
  PersonSimpleWalk, ShieldCheck, SlidersHorizontal, Trash, Users, Wheelchair, X,
} from "@phosphor-icons/react";
import { Toaster, toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { CityMap, type StreetRoute } from "@/components/CityMap";
import { AgentPanel } from "@/components/AgentPanel";
import { PlaceCard } from "@/components/PlaceCard";
import { PlaceDetails } from "@/components/PlaceDetails";
import { IntegrationsPanel } from "@/components/IntegrationsPanel";
import { OfficialEvents } from "@/components/ContextSources";
import { OpenUIResponse, type OpenUIConstraints } from "@/components/OpenUIResponse";
import { usePlanner } from "@/hooks/usePlanner";
import { usePlaceProfiles } from "@/hooks/usePlaceProfiles";
import { locations, scenarios } from "@/i18n";
import { readApiJson } from "@/lib/api";
import { advanceNavigationStep } from "@/lib/navigation-progress";
import { catalogDetail, type CatalogPlace } from "@/lib/place-catalog";
import type { Language, Place, Recommendation, Scenario } from "@/types";
const Voice = lazy(() => import("@/components/Voice"));
type Drawer = "saved" | "settings" | "route" | null;
type GeoPosition = { lat: number; lon: number; accuracy?: number; heading?: number };
type PublicPlace = Pick<Place, "id" | "name" | "lat" | "lon" | "category">;

function distance(a: GeoPosition, b: GeoPosition) {
  const r = Math.PI / 180, dlat = (b.lat - a.lat) * r, dlon = (b.lon - a.lon) * r;
  const n = Math.sin(dlat / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(dlon / 2) ** 2;
  return 6371000 * 2 * Math.asin(Math.min(1, Math.sqrt(n)));
}
function savedPlaces(): Place[] {
  try { return JSON.parse(localStorage.getItem("qala-saved") || "[]"); } catch { return []; }
}
const minutes = (seconds: number) => Math.max(1, Math.ceil(seconds / 60));

function App() {
  const planner = usePlanner();
  const { settings, result, loading, error, context } = planner;
  const { profiles, load: loadProfiles, clear: clearProfiles } = usePlaceProfiles(settings.language);
  const profileIntent = useRef(false);
  const update: typeof planner.update = (...args) => {
    profileIntent.current = true;
    clearProfiles();
    return planner.update(...args);
  };
  const tr = (en: string, ru: string) => settings.language === "ru" ? ru : en;
  const km = (meters: number) => meters < 1000 ? Math.round(meters) + tr(" m", " м") : (meters / 1000).toFixed(1) + tr(" km", " км");
  const interestLabel = (value: string) => settings.language === "ru" ? ({ coffee: "Кофе", nature: "Природа", culture: "Культура", museum: "Музеи", family: "С детьми", shopping: "Покупки", night: "Вечером", quiet: "Тихие места" }[value] ?? value) : value;
  const [drawer, setDrawer] = useState<Drawer>(null);
  const [evidence, setEvidence] = useState<Place | null>(null);
  const [catalogSelection, setCatalogSelection] = useState<CatalogPlace>();
  const [catalogRequest, setCatalogRequest] = useState<{ place: CatalogPlace; status: "loading" | "error" } | null>(null);
  const catalogRequestRef = useRef<AbortController | null>(null);
  const [selectedId, setSelectedId] = useState<string>();
  const [saved, setSaved] = useState<Place[]>(savedPlaces);
  const [voiceOpen, setVoiceOpen] = useState(false);
  const [assistantBusy, setAssistantBusy] = useState(false);
  const [prompt, setPrompt] = useState<{ id: string; text: string }>();
  const [mobileView, setMobileView] = useState<"map" | "assistant">("map");
  const [search, setSearch] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchIndex, setSearchIndex] = useState(-1);
  const [pois, setPois] = useState<PublicPlace[]>([]);
  const [memoryInterests, setMemoryInterests] = useState<string[]>([]);
  const [streetRoute, setStreetRoute] = useState<StreetRoute | null>(null);
  const [routing, setRouting] = useState(false);
  const [routeError, setRouteError] = useState("");
  const [routeRevision, setRouteRevision] = useState(0);
  const [navigating, setNavigating] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [userLocation, setUserLocation] = useState<GeoPosition>();
  const [locating, setLocating] = useState(false);
  const [following, setFollowing] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const evidenceOpenerRef = useRef<HTMLElement | null>(null);
  const watchRef = useRef<number | null>(null);
  const cardsRef = useRef<HTMLDivElement>(null);
  const pendingMapSelection = useRef<{ plan: Recommendation; id: string } | null>(null);
  const openEvidence = (place: Place) => {
    catalogRequestRef.current?.abort();
    setCatalogRequest(null);
    if (!evidence) {
      const active = document.activeElement;
      evidenceOpenerRef.current = active instanceof HTMLElement && active !== document.body ? active : null;
    }
    setEvidence(place);
    if (!profiles[place.id]) void loadProfiles([place.id, ...places.map(item => item.id)]);
  };
  const places = result?.recommendations ?? [];
  const busy = loading || assistantBusy;
  const visitMinutes = places.reduce((sum, place) => sum + place.visit_minutes, 0);
  const walkingMinutes = streetRoute ? streetRoute.legs.reduce((sum, leg) => sum + minutes(leg.duration_seconds), 0) : result?.route.walk_minutes ?? 0;
  const totalMinutes = streetRoute ? walkingMinutes + visitMinutes + 5 : result?.route.total_minutes ?? 0;
  const availableMinutes = Number(result?.context.available_minutes ?? settings.duration);
  const overBudget = totalMinutes > availableMinutes;
  const steps = useMemo(() => streetRoute?.legs.flatMap((leg, legIndex) =>
    leg.steps.map((step) => ({ ...step, legIndex }))) ?? [], [streetRoute]);
  const activeStep = steps[stepIndex];
  const warnings = Array.isArray(result?.context.missing_data) ?
    result.context.missing_data.filter((item): item is string => typeof item === "string") : [];
  const routeSetup = useMemo(() => {
    const origin = result?.route.coordinates[0];
    const coordinates: [number, number][] = origin ? [origin] : [];
    const legByPlace: (number | null)[] = [];
    let legIndex = 0;
    for (const place of places) {
      const previous = coordinates.at(-1);
      if (previous && distance({ lon: previous[0], lat: previous[1] }, place) < 1) legByPlace.push(null);
      else { coordinates.push([place.lon, place.lat]); legByPlace.push(legIndex++); }
    }
    return { coordinates, legByPlace };
  }, [result]);
  const routeCoordinates = routeSetup.coordinates;
  const hasWalkingPath = routeCoordinates.length >= 2;
  const canStart = planner.current && !busy && !routing && !overBudget;
  const legForPlace = (index: number) => {
    const legIndex = routeSetup.legByPlace[index];
    return legIndex === null ? { distance_m: 0, duration_seconds: 0 } : streetRoute?.legs[legIndex];
  };
  const presentedPlace = (place: Place, index: number): Place => {
    const leg = legForPlace(index);
    return leg ? { ...place, walk_minutes: leg.duration_seconds ? minutes(leg.duration_seconds) : 0,
      leg_distance_m: leg.distance_m } : place;
  };
  const coordinateKey = JSON.stringify(routeCoordinates);
  const navigationUrl = places.length ? "https://www.google.com/maps/dir/?api=1&origin=" +
    settings.location.lat + "," + settings.location.lon + "&destination=" + places.at(-1)!.lat + "," + places.at(-1)!.lon +
    "&travelmode=walking" + (places.length > 1 ? "&waypoints=" + places.slice(0, -1).map(p => p.lat + "," + p.lon).join("|") : "") : "";
  const matches = useMemo(() => {
    const text = search.trim().toLocaleLowerCase();
    if (text.length < 2) return [];
    return pois.filter(p => (p.name + " " + p.category).toLocaleLowerCase().includes(text)).slice(0, 7);
  }, [search, pois]);

  useEffect(() => {
    const controller = new AbortController();
    if (search.trim().length < 2) { setPois([]); return () => controller.abort(); }
    const timer = setTimeout(() => {
      const query = new URLSearchParams({ q: search.trim(), limit: "20" });
      void fetch("/api/pois?" + query, { signal: controller.signal }).then(r => readApiJson<{ pois: PublicPlace[] }>(r, "Place search unavailable."))
        .then(data => { if (!controller.signal.aborted) setPois(data.pois); }).catch(() => { if (!controller.signal.aborted) setPois([]); });
    }, 180);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [search]);
  useEffect(() => { setMemoryInterests(planner.memoryPreferences?.interests ?? []); }, [planner.memoryPreferences]);
  useEffect(() => { localStorage.setItem("qala-saved", JSON.stringify(saved)); }, [saved]);
  useEffect(() => {
    const keys = (event: KeyboardEvent) => {
      document.documentElement.dataset.input = "keyboard";
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault(); searchRef.current?.focus(); setSearchOpen(true);
      }
      if (event.key === "Escape") setSearchOpen(false);
    };
    const pointer = () => { document.documentElement.dataset.input = "pointer"; };
    window.addEventListener("keydown", keys); window.addEventListener("pointerdown", pointer);
    return () => { window.removeEventListener("keydown", keys); window.removeEventListener("pointerdown", pointer); };
  }, []);
  useEffect(() => {
    const pending = pendingMapSelection.current;
    setSelectedId(pending?.plan === result && places.some(place => place.id === pending.id) ? pending.id : places[0]?.id);
    pendingMapSelection.current = null;
    setNavigating(false); setStepIndex(0);
    if (watchRef.current !== null) navigator.geolocation.clearWatch(watchRef.current);
    watchRef.current = null; setFollowing(false); setUserLocation(undefined);
  }, [result]);
  useEffect(() => {
    clearProfiles();
    if (profileIntent.current && result && planner.current && !loading) {
      void loadProfiles(result.recommendations.map(place => place.id));
    }
  }, [result, settings.language, planner.current, loading, clearProfiles, loadProfiles]);
  useEffect(() => {
    const controller = new AbortController();
    setStreetRoute(null); setRouteError("");
    if (routeCoordinates.length < 2) { setRouting(false); return; }
    setRouting(true);
    void fetch("/api/navigation/route", {
      method: "POST", signal: controller.signal, headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ coordinates: routeCoordinates, language: settings.language }),
    }).then(r => readApiJson<StreetRoute>(r, "Walking directions are unavailable. Try again or open Maps."))
      .then(data => { if (!controller.signal.aborted) setStreetRoute(data); })
      .catch(reason => {
        if (!controller.signal.aborted) setRouteError(reason instanceof TypeError ?
          "Walking directions could not connect. Try again or open Maps." : reason.message);
      }).finally(() => { if (!controller.signal.aborted) setRouting(false); });
    return () => controller.abort();
  }, [coordinateKey, settings.language, routeRevision]);
  useEffect(() => () => {
    catalogRequestRef.current?.abort();
    if (watchRef.current !== null) navigator.geolocation.clearWatch(watchRef.current);
  }, []);
  useEffect(() => {
    if (planner.current && !busy) return;
    setNavigating(false); setFollowing(false);
    if (watchRef.current !== null) navigator.geolocation.clearWatch(watchRef.current);
    watchRef.current = null; setUserLocation(undefined);
  }, [planner.current, busy]);
  useEffect(() => {
    if (!following || !userLocation || !streetRoute) return;
    const next = advanceNavigationStep(userLocation, streetRoute.geometry.coordinates, steps, stepIndex);
    if (next !== stepIndex) setStepIndex(next);
  }, [userLocation, following, streetRoute, stepIndex, steps]);

  const selectPlace = (id: string, restoring?: Recommendation) => {
    setCatalogSelection(undefined);
    profileIntent.current = true;
    if (restoring && restoring !== result) pendingMapSelection.current = { plan: restoring, id };
    else if (!profiles[id]) void loadProfiles([id, ...places.map(place => place.id)]);
    setSelectedId(id); setMobileView("map");
    cardsRef.current?.querySelector<HTMLElement>('[data-place-id="' + id + '"]')?.scrollIntoView({ block: "nearest", inline: "nearest" });
  };
  const ask = (text: string) => {
    profileIntent.current = true;
    clearProfiles();
    planner.setLastQuery(text); setAssistantBusy(true); setPrompt({ id: crypto.randomUUID(), text }); setMobileView("assistant");
  };
  const refine = (patch: OpenUIConstraints) => {
    update(patch, false);
    ask(settings.language === "ru" ? "Обнови этот план с выбранными настройками." : settings.language === "kk" ? "Таңдалған параметрлермен жоспарды жаңарт." : "Update this plan with the selected preferences.");
  };
  const openMemory = () => {
    setDrawer("settings");
    void planner.inspectMemory().catch(reason => toast.error(reason.message));
    requestAnimationFrame(() => document.getElementById("preference-memory")?.focus());
  };
  const runScenario = (scenario: Scenario) => {
    update({ location: scenario.location, duration: scenario.minutes, plannedTime: scenario.id === "night" ? "20:00" : "14:00" }, false);
    ask(scenario.message[settings.language]);
  };
  const openCatalogPlace = (place: CatalogPlace) => {
    catalogRequestRef.current?.abort();
    const controller = new AbortController();
    catalogRequestRef.current = controller;
    const active = document.activeElement;
    evidenceOpenerRef.current = active instanceof HTMLElement && active !== document.body ? active : null;
    setEvidence(null); setCatalogRequest({ place, status: "loading" });
    setCatalogSelection(place); setMobileView("map");
    void fetch("/api/pois/" + encodeURIComponent(place.id), { signal: controller.signal })
      .then(response => readApiJson<{ poi: Record<string, unknown> }>(response, "Place unavailable"))
      .then(data => {
        if (controller.signal.aborted) return;
        const detail = catalogDetail(data.poi, settings.language);
        setEvidence(detail); setCatalogRequest(null);
        void loadProfiles([detail.id, ...places.map(item => item.id)]);
      }).catch(() => { if (!controller.signal.aborted) setCatalogRequest({ place, status: "error" }); });
  };
  const choosePlace = (place: PublicPlace) => {
    setSearch(""); setSearchOpen(false); setSearchIndex(-1); setMobileView("map");
    openCatalogPlace(place);
  };
  const savePlace = (place: Place) => {
    const has = saved.some(p => p.id === place.id);
    setSaved(old => has ? old.filter(p => p.id !== place.id) : [...old, place]);
    toast(has ? tr("Removed from saved places", "Место удалено из сохранённого") : tr("Place saved", "Место сохранено"));
  };
  const geolocationError = (reason: GeolocationPositionError) => {
    if (watchRef.current !== null) navigator.geolocation.clearWatch(watchRef.current);
    watchRef.current = null;
    setLocating(false); setFollowing(false);
    toast.error(reason.code === 1 ? tr("Location access declined. You can still choose a starting point.", "Доступ к геолокации отклонён. Выберите отправную точку вручную.") :
      tr("Your location could not be found. Try again outdoors.", "Не удалось определить геолокацию. Попробуйте ещё раз на улице."));
  };
  const locate = () => {
    if (!navigator.geolocation) { toast.error(tr("This browser does not support location.", "Браузер не поддерживает геолокацию.")); return; }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(position => {
      setLocating(false);
      const { latitude: lat, longitude: lon } = position.coords;
      if (lat < 50.95 || lat > 51.35 || lon < 71.15 || lon > 71.75) {
        toast(tr("Qala covers Astana. Choose a landmark to explore from wherever you are.", "Qala работает с Астаной. Выберите отправную точку на карте.")); return;
      }
      update({ location: { lat, lon, label: tr("Your location", "Моя геолокация") } });
    }, geolocationError, { enableHighAccuracy: true, timeout: 12000, maximumAge: 30000 });
  };
  const toggleFollow = () => {
    if (following) {
      if (watchRef.current !== null) navigator.geolocation.clearWatch(watchRef.current);
      watchRef.current = null; setFollowing(false); return;
    }
    if (!navigator.geolocation) { toast.error(tr("This browser does not support location.", "Браузер не поддерживает геолокацию.")); return; }
    setFollowing(true);
    watchRef.current = navigator.geolocation.watchPosition(position => {
      setUserLocation({ lat: position.coords.latitude, lon: position.coords.longitude,
        accuracy: position.coords.accuracy, heading: position.coords.heading ?? undefined });
    }, geolocationError, { enableHighAccuracy: true, timeout: 15000, maximumAge: 5000 });
  };
  const startWalking = () => {
    if (!streetRoute || !canStart) { setDrawer("route"); return; }
    setNavigating(true); setStepIndex(0); setMobileView("map"); setDrawer("route");
  };
  const shortenPlan = () => {
    if (!result || places.length < 2) return;
    const shorter = places.slice(0, -1);
    planner.setResult({ ...result, recommendations: shorter, route: {
      ...result.route, coordinates: [result.route.coordinates[0], ...shorter.map(p => [p.lon, p.lat] as [number, number])],
    } });
  };
  const downloadRoute = () => {
    if (!streetRoute) return;
    const points = streetRoute.geometry.coordinates.map(([lon, lat]) => '<trkpt lat="' + lat + '" lon="' + lon + '"/>').join("");
    const content = '<?xml version="1.0" encoding="UTF-8"?><gpx version="1.1" creator="Qala" xmlns="http://www.topografix.com/GPX/1/1"><metadata><name>Qala Astana walking route</name><desc>OSM pedestrian geometry via Valhalla; temporary closures and entrances unverified.</desc></metadata><trk><name>Astana walk</name><trkseg>' + points + "</trkseg></trk></gpx>";
    const url = URL.createObjectURL(new Blob([content], { type: "application/gpx+xml" }));
    const link = document.createElement("a"); link.href = url; link.download = "qala-astana-walk.gpx"; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const outsideRoute = userLocation && streetRoute ?
    streetRoute.geometry.coordinates.every(([lon, lat]) => distance(userLocation, { lat, lon }) > 150) : false;

  return (
    <div className="qala-app">
      <a href="#city-map" className="skip-link">{tr("Skip to map", "Перейти к карте")}</a>
      <header className="app-header">
        <a className="wordmark" href="/" aria-label={tr("Qala home", "Главная Qala")}><Compass weight="fill" />qala</a>
        <div className="global-search">
          <MagnifyingGlass size={19} />
          <input ref={searchRef} aria-label={tr("Find a place in Astana", "Найти место в Астане")} role="combobox" aria-expanded={searchOpen}
            aria-controls="place-search-results" aria-autocomplete="list"
            aria-activedescendant={searchIndex >= 0 ? "search-result-" + searchIndex : undefined}
            placeholder={tr("Search places, or ask Qala…", "Найдите место или спросите Qala…")} value={search}
            onFocus={() => setSearchOpen(true)} onBlur={() => setTimeout(() => setSearchOpen(false), 160)}
            onChange={e => { setSearch(e.target.value); setSearchOpen(true); setSearchIndex(-1); }}
            onKeyDown={e => {
              if (e.key === "ArrowDown") { e.preventDefault(); setSearchIndex(i => Math.min(i + 1, matches.length)); }
              if (e.key === "ArrowUp") { e.preventDefault(); setSearchIndex(i => Math.max(i - 1, -1)); }
              if (e.key === "Enter" && search.trim()) {
                e.preventDefault(); if (searchIndex >= 0 && matches[searchIndex]) choosePlace(matches[searchIndex]);
                else { ask(search); setSearch(""); setSearchOpen(false); }
              }
            }} />
          <kbd>⌘ K</kbd>
          {searchOpen && search.trim().length >= 2 && (
            <div className="search-results" id="place-search-results" role="listbox">
              {matches.map((place, index) => <button id={"search-result-" + index} key={place.id} role="option"
                aria-selected={searchIndex === index} onMouseDown={e => e.preventDefault()} onClick={() => choosePlace(place)}>
                <MapPin size={18} /><span><strong>{place.name}</strong><small>{place.category.replaceAll("_", " ")}</small></span><ArrowRight size={15} />
              </button>)}
              <button id={"search-result-" + matches.length} role="option" aria-selected={searchIndex === matches.length} onMouseDown={e => e.preventDefault()} onClick={() => { ask(search); setSearch(""); setSearchOpen(false); }}>
                <ChatCircleDots size={19} /><span>{tr("Ask Qala about", "Спросить Qala о")} «{search}»</span><ArrowRight size={15} />
              </button>
            </div>
          )}
        </div>
        <div className="header-actions">
          <Select value={settings.language} onValueChange={v => update({ language: v as Language })}>
            <SelectTrigger aria-label={tr("Language", "Язык")} className="language-select"><GlobeHemisphereWest size={18} /><SelectValue /></SelectTrigger>
            <SelectContent><SelectGroup><SelectItem value="en">EN</SelectItem><SelectItem value="ru">RU</SelectItem><SelectItem value="kk">KZ</SelectItem></SelectGroup></SelectContent>
          </Select>
          <Button variant="ghost" size="icon" aria-label={tr("Saved places", "Сохранённые места")} onClick={() => setDrawer("saved")}><BookmarkSimple /></Button>
          <Button className="header-voice" onClick={() => setVoiceOpen(true)} variant="outline"><Microphone />{tr("Talk to Qala", "Поговорить с Qala")}</Button>
        </div>
      </header>

      <main className="workspace" data-mobile-view={mobileView}>
        <nav className="app-rail" aria-label={tr("Main navigation", "Навигация")}>
          <button className={mobileView === "map" ? "rail-button active" : "rail-button"} onClick={() => { setMobileView("map"); setDrawer(null); }} aria-label={tr("Explore map", "Открыть карту")} title={tr("Explore map", "Открыть карту")}><Compass weight={mobileView === "map" ? "fill" : "regular"} /><span>{tr("Explore", "Карта")}</span></button>
          <button className={mobileView === "assistant" ? "rail-button active" : "rail-button"} onClick={() => setMobileView("assistant")} aria-label={tr("Assistant", "Ассистент")} title={tr("Assistant", "Ассистент")}><ChatCircleDots /><span>{tr("Assistant", "Ассистент")}</span></button>
          <button className="rail-button" onClick={() => setDrawer("route")} aria-label={tr("Walking itinerary", "Пеший маршрут")} title={tr("Walking itinerary", "Пеший маршрут")}><MapTrifold /><span>{tr("Itinerary", "Маршрут")}</span></button>
          <button className="rail-button" onClick={() => setDrawer("saved")} aria-label={tr("Open saved places", "Сохранённые места")} title={tr("Saved places", "Сохранённые места")}><BookmarkSimple /><span>{tr("Saved", "Сохранённое")}</span>{saved.length > 0 && <i className="rail-count">{saved.length}</i>}</button>
          <button className="rail-button rail-settings" onClick={() => setDrawer("settings")} aria-label={tr("Preferences and privacy", "Настройки и приватность")} title={tr("Preferences and privacy", "Настройки и приватность")}><SlidersHorizontal /><span>{tr("Settings", "Настройки")}</span></button>
        </nav>
        <aside className="assistant-pane" aria-label={tr("Qala assistant", "Ассистент Qala")}>
          <AgentPanel language={settings.language} context={context} onResult={(next, requestContext) => { profileIntent.current = true; planner.acceptResult(next, requestContext); }}
            onBusyChange={setAssistantBusy} onPlaceSelect={selectPlace} onVoice={() => setVoiceOpen(true)}
            onMemory={openMemory} remember={planner.remember}
            renderGenerativeUI={(original, routed, selectFromAnswer) => original.openui ? <OpenUIResponse key={original.openui.document} result={routed} language={settings.language} profiles={profiles} savedIds={saved.map(place => place.id)} onSelect={selectFromAnswer} onInspect={openEvidence} onSave={savePlace} onFollowUp={ask} onRefine={refine} /> : null}
            prompt={prompt} onQuery={text => { profileIntent.current = true; clearProfiles(); planner.setLastQuery(text); }}
            routedPlan={result && streetRoute ? { original: result, totalMinutes, walkingMinutes,
              distance: streetRoute.distance_m, stops: places.map((place, index) => ({
                id: place.id, walkMinutes: legForPlace(index)?.duration_seconds ? minutes(legForPlace(index)!.duration_seconds) : 0,
                distance: legForPlace(index)?.distance_m ?? 0,
              })), warnings: streetRoute.warnings ?? [], limitations: streetRoute.limitations ?? "Walking times are estimates. Confirm entrances and current access." } : undefined} />
        </aside>
        <section className="map-stage" id="city-map" aria-label={tr("Explore Astana", "Карта Астаны")}>
          <CityMap location={settings.location} result={result} language={settings.language} onRoute={() => setDrawer("route")}
            selectedId={selectedId} onSelectPlace={selectPlace} navigation={streetRoute} navigating={navigating}
            catalogSelection={catalogSelection} onCatalogSelect={openCatalogPlace}
            userLocation={userLocation} insetBottom={places.length ? 270 : 100} />
          <div className="map-top">
            <div className="context-bar">
              <div className="start-context"><MapPin weight="fill" size={17} /><Select value={String(locations.findIndex(p => Math.abs(p.lat - settings.location.lat) < .001 && Math.abs(p.lon - settings.location.lon) < .001))}
                onValueChange={v => { const place = locations[Number(v)]; if (place) update({ location: place }); }}>
                <SelectTrigger aria-label={tr("Starting point", "Отправная точка")}><span>{settings.location.label.split(" · ")[0]}</span></SelectTrigger>
                <SelectContent><SelectGroup>{locations.map((place, i) => <SelectItem key={place.label} value={String(i)}>{place.label}</SelectItem>)}</SelectGroup></SelectContent>
              </Select></div>
              <div className="context-divider" />
              <Select value={String(settings.duration)} onValueChange={v => update({ duration: Number(v) })}>
                <SelectTrigger aria-label={tr("Time available", "Свободное время")} className="time-context"><Clock size={16} /><SelectValue /></SelectTrigger>
                <SelectContent><SelectGroup>{[...new Set([15,30,45,60,90,120,180,settings.duration])].sort((a,b) => a-b).map(n => <SelectItem value={String(n)} key={n}>{n} {tr("min", "мин")}</SelectItem>)}</SelectGroup></SelectContent>
              </Select>
              <button className="filters-trigger" onClick={() => setDrawer("settings")} aria-label={tr("Adjust preferences", "Изменить настройки")}><SlidersHorizontal size={18} /><span>{tr("Preferences", "Настройки")}</span>{(settings.accessible || settings.indoor || settings.group > 1) && <b>{Number(settings.accessible)+Number(settings.indoor)+Number(settings.group>1)}</b>}</button>
              <button className="locate-trigger" onClick={locate} disabled={locating} aria-label={tr("Use my location", "Моя геолокация")} title={tr("Use my location", "Моя геолокация")}>{locating ? <CircleNotch className="spin" size={19} /> : <NavigationArrow size={18} />}</button>
            </div>
            <div className="scenario-chips" aria-label={tr("Ideas for your time", "Сценарии прогулки")}>
              {scenarios.map(s => <button data-testid={"scenario-" + s.id} key={s.id} onClick={() => runScenario(s)}>
                {s.icon === "coffee" ? <Coffee /> : s.icon === "kids" ? <Users /> : s.icon === "flight" ? <NavigationArrow /> : s.icon === "night" ? <Compass /> : <PersonSimpleWalk />}
                {s.labels[settings.language]}
              </button>)}
              <button data-testid="scenario-events" onClick={() => ask(({en:"What upcoming events are in the official calendar?",ru:"Какие ближайшие события есть в официальной афише?",kk:"Ресми афишада қандай алдағы іс-шаралар бар?"})[settings.language])}><CalendarDots />{({en:"Events",ru:"Афиша",kk:"Афиша"})[settings.language]}</button>
            </div>
          </div>
          {(busy || error) && <div className={"map-status" + (error ? " error" : "")} role={error ? "alert" : "status"}>
            {busy ? <><CircleNotch className="spin" />{tr("Finding places that fit your time…", "Ищу места под ваш лимит времени…")}</> : <><Info />{error}<button onClick={() => void planner.plan(planner.lastQuery)}>{tr("Try again", "Повторить")}</button></>}
          </div>}
          {!busy && result && !places.length && result.context.event_only_request === true && <div className="event-map-state">
            {result.events?.length ? <OfficialEvents events={result.events} language={settings.language} /> : <><h2><CalendarDots />{tr("Events", "Афиша")}</h2><p>{result.message}</p><a href="https://a-vm.kz/events/" target="_blank" rel="noreferrer">{tr("Open official calendar", "Официальная афиша")}<ArrowSquareOut /></a></>}
          </div>}
          {!busy && result && !places.length && result.context.event_only_request !== true && <div className="empty-map-state">
            <Compass size={28} /><h2>{tr("No matching places", "Подходящих мест нет")}</h2><p>{result.message}</p>
            <Button onClick={() => update({ duration: 90, accessible: false, indoor: false })}>{tr("Try a wider plan", "Расширить условия")}<ArrowRight /></Button>
          </div>}
          {places.length > 0 && <div className="map-bottom">
            {overBudget && streetRoute && <div className="budget-notice" role="status"><Clock size={16} /><span>{settings.language === "ru" ? `Маршрут по улицам займёт ${totalMinutes} мин при лимите ${availableMinutes} мин.` : `The street route needs ${totalMinutes} min, above your ${availableMinutes} min limit.`}</span>
              {places.length > 1 ? <button onClick={shortenPlan}>{tr("Remove last stop", "Убрать последнюю остановку")}</button> : <button onClick={() => update({ duration: Math.min(180, Math.ceil(totalMinutes / 30) * 30) })}>{tr("Add time", "Добавить время")}</button>}
            </div>}
            <div className="stop-cards" ref={cardsRef} aria-label={tr("Your recommended places", "Рекомендованные места")}>
              {places.map((place, index) => <PlaceCard key={place.id} place={presentedPlace(place, index)}
                index={index} language={settings.language} profile={profiles[place.id]} saved={saved.some(p => p.id === place.id)} selected={selectedId === place.id}
                onSelect={() => selectPlace(place.id)} onSave={() => savePlace(place)} onEvidence={() => openEvidence(presentedPlace(place, index))} />)}
            </div>
            <div className="itinerary-bar">
              <div className="itinerary-symbol"><PersonSimpleWalk size={27} /></div>
              <button className="itinerary-title" onClick={() => setDrawer("route")}><strong>{!streetRoute && hasWalkingPath ? "≈ " : ""}{totalMinutes} {tr("min", "мин")} · {km(streetRoute?.distance_m ?? result!.route.distance_m)}</strong>
                <span>{settings.language === "ru" ? `Остановок: ${places.length}` : settings.language === "kk" ? `Аялдама: ${places.length}` : `${places.length} ${places.length === 1 ? "stop" : "stops"}`}</span></button>
              {routing && <CircleNotch className="spin route-loading" aria-label={tr("Finding walking directions", "Строю пеший маршрут")} />}
              <Button className="start-walk" onClick={!hasWalkingPath ? () => openEvidence(presentedPlace(places[0], 0)) : streetRoute ? startWalking : () => setDrawer("route")} disabled={routing || busy || !planner.current}>
                {routing ? <CircleNotch className="spin" /> : null}{navigating ? tr("Directions", "Инструкции") : !hasWalkingPath ? tr("View place", "Открыть место") : overBudget ? tr("Review plan", "Проверить план") : tr("Start walking", "Начать прогулку")}<ArrowRight />
              </Button>
            </div>
          </div>}
        </section>
      </main>

      <Sheet open={drawer !== null} onOpenChange={open => { if (!open) setDrawer(null); }}>
        <SheetContent className={"detail-sheet " + (drawer === "route" ? "route-sheet" : "")}>
          <SheetHeader><SheetTitle>{drawer === "saved" ? tr("Saved places", "Сохранённые места") : drawer === "settings" ? tr("Preferences", "Настройки") : navigating ? tr("Walking directions", "Пошаговый маршрут") : tr("Walking route", "Пеший маршрут")}</SheetTitle>
            <SheetDescription className="sr-only">{drawer === "saved" ? tr("Saved places", "Сохранённые места") : drawer === "settings" ? tr("Route preferences and memory controls", "Параметры маршрута и управление памятью") : tr("Walking route and navigation controls", "Пеший маршрут и управление навигацией")}</SheetDescription></SheetHeader>
          <div className="sheet-body">
            {drawer === "settings" && <>
              <section className="settings-section"><h3>{tr("Your plans", "Параметры прогулки")}</h3>
                <label className="settings-row"><span><Clock /><b>{tr("When are you heading out?", "Когда планируете выйти?")}</b></span><Select value={settings.plannedTime} onValueChange={v => update({ plannedTime: v })}>
                  <SelectTrigger aria-label={tr("Departure time", "Время выхода")}><SelectValue /></SelectTrigger><SelectContent><SelectGroup><SelectItem value="now">{tr("Now", "Сейчас")}</SelectItem>{["09:00","12:00","14:00","17:00","20:00","23:00"].map(time => <SelectItem value={time} key={time}>{tr("Today", "Сегодня")} {time}</SelectItem>)}</SelectGroup></SelectContent></Select></label>
                <label className="settings-row"><span><Users /><b>{tr("Who's coming?", "Кто идёт?")}</b></span><Select value={String(settings.group)} onValueChange={v => update({ group: Number(v) })}>
                  <SelectTrigger aria-label={tr("Group size", "Размер группы")}><SelectValue /></SelectTrigger><SelectContent><SelectGroup>{[1,2,3,4,5].map(n => <SelectItem value={String(n)} key={n}>{n === 1 ? tr("Just me", "Один человек") : n + tr(" people", " человек")}</SelectItem>)}</SelectGroup></SelectContent></Select></label>
                <label className="settings-row"><span><MapPin /><b>{tr("Stay indoors", "Только в помещении")}</b></span><Switch aria-label={tr("Indoor places only", "Только крытые места")} checked={settings.indoor} onCheckedChange={v => update({ indoor: v })} /></label>
                <label className="settings-row"><span><Wheelchair /><span><b>{tr("Wheelchair access listed", "Доступность на коляске указана")}</b><small>{tr("Venue tags, not verified step-free streets.", "Данные о месте, а не проверка всех переходов.")}</small></span></span><Switch aria-label={tr("Wheelchair access listed", "Доступность на коляске указана")} checked={settings.accessible} onCheckedChange={v => update({ accessible: v })} /></label>
                <label className="settings-row"><span><NavigationArrow /><span><b>{tr("Airport transfer", "Дорога до аэропорта")}</b><small>{tr("Your current estimate, before airport reserve.", "Ваша оценка дороги, отдельно от запаса на аэропорт.")}</small></span></span><Select value={settings.airportTransfer === null ? "unknown" : String(settings.airportTransfer)} onValueChange={v => update({ airportTransfer: v === "unknown" ? null : Number(v) })}>
                  <SelectTrigger aria-label={tr("Airport transfer estimate", "Время до аэропорта")}><SelectValue /></SelectTrigger><SelectContent><SelectGroup><SelectItem value="unknown">{tr("Not sure yet", "Пока не знаю")}</SelectItem>{[20,30,45,60,90].map(n => <SelectItem value={String(n)} key={n}>{n} {tr("min", "мин")}</SelectItem>)}</SelectGroup></SelectContent></Select></label>
              </section>
              <section className="settings-section" id="preference-memory" tabIndex={-1}><h3>{tr("Preference memory", "Память предпочтений")}</h3>
                <label className="settings-row"><span><ShieldCheck /><span><b>{tr("Remember my preferences", "Запоминать предпочтения")}</b></span></span><Switch id="remember" aria-label={tr("Remember my preferences", "Запоминать предпочтения")} disabled={planner.memoryBusy} checked={planner.remember} onCheckedChange={v => void planner.changeRemember(v).catch(e => toast.error(e.message))} /></label>
                {planner.memoryPreferences && <div className="memory-inspector"><dl><div><dt>{tr("Stored interests", "Сохранённые интересы")}</dt><dd>{planner.memoryPreferences.interests?.map(interestLabel).join(", ") || tr("None selected", "Не выбраны")}</dd></div><div><dt>{tr("Time preference", "Время прогулки")}</dt><dd>{planner.memoryPreferences.duration_minutes ?? settings.duration} {tr("min", "мин")}</dd></div><div><dt>{tr("Retention", "Срок хранения")}</dt><dd>{planner.memoryPreferences.retention_days ?? 30} {tr("days", "дней")}</dd></div></dl>
                  <fieldset><legend>{tr("Edit remembered interests", "Изменить интересы в памяти")}</legend><div>{["coffee", "nature", "culture", "museum", "family", "shopping", "night", "quiet"].map(interest => <label key={interest}><input type="checkbox" value={interest} checked={memoryInterests.includes(interest)} onChange={event => setMemoryInterests(old => event.target.checked ? [...old, interest] : old.filter(value => value !== interest))} /><span>{interestLabel(interest)}</span></label>)}</div></fieldset>
                  <Button variant="outline" disabled={planner.memoryBusy} onClick={() => void planner.editMemory(memoryInterests).then(() => toast(tr("Preferences saved", "Предпочтения сохранены"))).catch(reason => toast.error(reason.message))}>{tr("Save preferences", "Сохранить предпочтения")}</Button>
                </div>}
                <Button variant="outline" disabled={planner.memoryBusy} onClick={() => void planner.changeRemember(false).then(() => toast(tr("Preferences deleted", "Предпочтения удалены"))).catch(e => toast.error(e.message))}><Trash />{tr("Forget my preferences", "Удалить мои предпочтения")}</Button>
              </section>
              <details className="settings-services"><summary>{tr("Data and services", "Данные и сервисы")}<CaretRight aria-hidden="true" /></summary><IntegrationsPanel language={settings.language} /></details>
            </>}
            {drawer === "saved" && (saved.length ? <><div className="saved-list">{saved.map(place => <div className="saved-place" key={place.id}>
              <MapPin /><button onClick={() => { choosePlace(place); setDrawer(null); }}><strong>{place.name}</strong><small>{place.category}</small></button>
              <Button variant="ghost" size="icon" aria-label={(settings.language === "ru" ? "Удалить " : "Remove ") + place.name} onClick={() => savePlace(place)}><X /></Button>
            </div>)}</div><Button variant="outline" onClick={() => setSaved([])}><Trash />{tr("Clear saved places", "Очистить сохранённое")}</Button></> :
              <div className="drawer-empty"><BookmarkSimple size={35} /><h3>{tr("No saved places", "Нет сохранённых мест")}</h3><p>{tr("Save places with their bookmark button.", "Сохраняйте места кнопкой закладки.")}</p></div>)}
            {drawer === "route" && <>
              <div className="route-overview"><div><strong>{totalMinutes}<small>{tr("min total", "мин всего")}</small></strong><span>{walkingMinutes} {tr("min walking", "мин пешком")} · {visitMinutes} {tr("min visiting", "мин на месте")} · 5 {tr("min buffer", "мин запас")}</span></div><span className="route-distance">{km(streetRoute?.distance_m ?? result?.route.distance_m ?? 0)}</span></div>
              {routing && <p className="route-service-note"><CircleNotch className="spin" />{tr("Finding the actual walking paths…", "Прокладываю путь по пешеходным улицам…")}</p>}
              {routeError && <div className="route-error" role="alert"><Info /><p>{routeError}</p><Button variant="outline" onClick={() => setRouteRevision(v => v + 1)}>{tr("Try routing again", "Повторить построение")}</Button></div>}
              {overBudget && <p className="route-warning">{tr("This route exceeds your time budget. Remove a stop or allow more time before starting.", "Маршрут превышает ваш лимит времени. Уберите остановку или добавьте время.")}</p>}
              {streetRoute?.warnings?.map((warning, index) => <p className="route-warning" key={index}>{warning}</p>)}
              {!hasWalkingPath && places.length > 0 && <p className="route-service-note">{tr("You’re already at this stop.", "Вы уже у этой остановки.")}</p>}
              <ol className="route-stops">{places.map((place, i) => <li key={place.id}><span>{i+1}</span><div><button onClick={() => { selectPlace(place.id); setDrawer(null); }}>{place.name}<ArrowSquareOut size={14} /></button><p>{place.action}</p><small>{place.visit_minutes} {tr("min here", "мин на месте")} · {legForPlace(i) ? (legForPlace(i)!.duration_seconds ? minutes(legForPlace(i)!.duration_seconds) : 0) : place.walk_minutes} {tr("min walking to this stop", "мин пешком до этой остановки")}</small></div></li>)}</ol>
              {streetRoute && <><div className="route-actions"><Button disabled={!canStart} onClick={startWalking}>{navigating ? <Check /> : <PersonSimpleWalk />}{navigating ? tr("Directions active", "Маршрут открыт") : tr("Start directions", "Открыть инструкции")}</Button><Button variant="outline" onClick={downloadRoute}><DownloadSimple />GPX</Button></div>
                {navigating && activeStep && <section className="walking-navigation">
                  <div className="turn-heading"><NavigationArrow weight="fill" /><span>{tr("Step", "Шаг")} {stepIndex + 1} {tr("of", "из")} {steps.length}<small>{following ? tr("Following your location", "Следую за вашей геолокацией") : tr("Manual preview", "Просмотр вручную")}</small></span><strong>{km(activeStep.distance_m)}</strong></div>
                  <h3>{activeStep.instruction}</h3>
                  <div className="turn-controls"><Button variant="outline" disabled={stepIndex === 0} onClick={() => setStepIndex(i => i - 1)}><CaretLeft />{tr("Back", "Назад")}</Button><Button disabled={stepIndex >= steps.length - 1} onClick={() => setStepIndex(i => i + 1)}>{tr("Next turn", "Следующий поворот")}<CaretRight /></Button></div>
                  <Button className="follow-location" variant="outline" onClick={toggleFollow}><NavigationArrow />{following ? tr("Stop location updates", "Остановить геолокацию") : tr("Use live location", "Включить геолокацию")}</Button>
                  {outsideRoute && <p className="route-warning">{tr("You are away from this route. Return to the path or open Maps for a new route.", "Вы отошли от маршрута. Вернитесь к пути или постройте новый в Картах.")}</p>}
                  <Button variant="ghost" onClick={() => { setNavigating(false); if (watchRef.current !== null) navigator.geolocation.clearWatch(watchRef.current); watchRef.current = null; setFollowing(false); setUserLocation(undefined); }}>{tr("End navigation", "Завершить навигацию")}</Button>
                </section>}
                <details className="all-directions"><summary>{tr("All", "Все")} {steps.length} {tr("walking instructions", "пеших инструкций")}</summary><ol>{steps.map((step, i) => <li key={i}><button disabled={!canStart} onClick={() => { if (canStart) { setNavigating(true); setStepIndex(i); } }}>{step.instruction}<small>{km(step.distance_m)}</small></button></li>)}</ol></details>
              </>}
              {navigationUrl && <a className="external-directions" href={navigationUrl} target="_blank" rel="noreferrer">{tr("Open walking directions in Maps", "Открыть пеший маршрут в Картах")}<ArrowSquareOut size={17} /></a>}
              <details className="route-caveats"><summary><Info size={15} />{tr("Before you go", "Перед прогулкой")}</summary>{warnings.map((text, i) => <p key={i}>{text}</p>)}<p>{tr("Walking times are estimates. Entrances, temporary closures and step-free access are not verified.", "Время пешком приблизительное. Входы, временные перекрытия и отсутствие ступеней не проверены.")}</p>
                {streetRoute && <p>{tr("Routing: Valhalla · © OpenStreetMap contributors. Selected coordinates are sent to the routing provider; no messages or preference IDs are sent.", "Маршрут: Valhalla · © участники OpenStreetMap. Провайдер получает выбранные координаты без переписки и идентификатора предпочтений.")}</p>}
                {settings.language === "kk" && streetRoute && <p>Kazakh turn instructions are unavailable; navigation instructions are shown in English.</p>}
              </details>
            </>}
          </div>
        </SheetContent>
      </Sheet>
      <Dialog open={Boolean(evidence || catalogRequest)} onOpenChange={open => { if (!open) { catalogRequestRef.current?.abort(); setEvidence(null); setCatalogRequest(null); } }}>
        <DialogContent className="evidence-dialog" onCloseAutoFocus={event => {
          event.preventDefault();
          const opener = evidenceOpenerRef.current;
          const visible = opener?.isConnected && opener.getClientRects().length > 0
            && getComputedStyle(opener).visibility !== "hidden" && !opener.matches(":disabled")
            && !opener.closest("[inert], [aria-hidden='true']");
          (visible ? opener : searchRef.current)?.focus({ preventScroll: true });
          evidenceOpenerRef.current = null;
        }}><DialogHeader><DialogTitle>{evidence?.name || catalogRequest?.place.name}</DialogTitle><DialogDescription className="sr-only">{tr("Place data and sources", "Сведения о месте и источники")}</DialogDescription></DialogHeader>
          {catalogRequest?.status === "loading" && <div className="catalog-detail-loading" role="status"><CircleNotch className="animate-spin" />{tr("Loading place…", "Загружаем место…")}</div>}
          {catalogRequest?.status === "error" && <div className="catalog-detail-loading" role="alert"><p>{tr("This place couldn’t load", "Не удалось загрузить место")}</p><Button variant="outline" onClick={() => openCatalogPlace(catalogRequest.place)}>{tr("Try again", "Повторить")}</Button></div>}
          {evidence && <PlaceDetails place={evidence} language={settings.language} profile={profiles[evidence.id]} saved={saved.some(place => place.id === evidence.id)}
            onMap={() => { if (evidence.catalog_only) setCatalogSelection({ id: evidence.id, name: evidence.name, lat: evidence.lat, lon: evidence.lon, category: evidence.category }); else selectPlace(evidence.id); setEvidence(null); }} onSave={() => savePlace(evidence)} onRefresh={() => void loadProfiles([evidence.id, ...places.map(place => place.id)], { force: true })} />}
        </DialogContent>
      </Dialog>
      {voiceOpen && <Suspense fallback={null}><Voice open={voiceOpen} onOpenChange={setVoiceOpen} language={settings.language} onTranscript={planner.setLastQuery} onDictation={ask} onRecommendation={planner.acceptResult}
        context={JSON.stringify({ ...context, session_id: undefined, remember: undefined })} /></Suspense>}
      <Toaster position="bottom-center" richColors closeButton />
    </div>
  );
}
export default App;
