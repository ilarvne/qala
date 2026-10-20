import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { ArrowClockwise, ArrowSquareOut, Compass, Crosshair, Minus, Plus, WifiSlash, Footprints, MapPin, CircleNotch } from "@phosphor-icons/react";
import { AttributionControl, LngLatBounds, Map as MapLibreMap, Marker, setWorkerUrl, type GeoJSONSource } from "maplibre-gl";
import mapWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type { CityMapProps } from "@/components/map-types";
import { useMapControlsInset } from "@/lib/use-map-controls-inset";
import { prepareCityStyle, setCityMapDepth, setCityMapLanguage } from "@/lib/city-map-style";
import { addCatalogLayers, CATALOG_CLUSTERS, CATALOG_POINTS, CATALOG_SOURCE, selectedCatalogData } from "@/lib/city-map-catalog";
import { usePlaceCatalog } from "@/hooks/usePlaceCatalog";
import { PlaceCatalogBrowser } from "@/components/PlaceCatalogBrowser";
import { catalogPlace, type CatalogFeature } from "@/lib/place-catalog";
import "maplibre-gl/dist/maplibre-gl.css";
import "@/styles/map.css";

// MapLibre v6's worker is a separate ESM entry. Let Vite bundle and emit it
// so production maps can decode vector tiles from the same origin.
setWorkerUrl(mapWorkerUrl);

const STYLE_URL = "https://tiles.openfreemap.org/styles/positron";
const EMPTY_LINE = { type: "FeatureCollection" as const, features: [] };
const text = {
  en: { map: "Interactive city map", zoomIn: "Zoom in", zoomOut: "Zoom out", recenter: "Back to your location", north: "Reset bearing to north", flat: "Switch to 2D map", depth: "Switch to 3D map", loading: "Bringing the city into view", unavailable: "The map couldn’t load", error: "Your places are still here. Try again or open the map in a new tab.", retry: "Try again", external: "Open map", connection: "Some map details couldn’t load", estimated: "Suggested stops · distances estimated", walking: "Walking route", active: "Navigation active", start: "Starting point", gps: "Your current location" },
  ru: { map: "Интерактивная карта города", zoomIn: "Приблизить", zoomOut: "Отдалить", recenter: "К вашему местоположению", north: "Ориентировать на север", flat: "Карта в 2D", depth: "Карта в 3D", loading: "Открываем город", unavailable: "Не удалось загрузить карту", error: "Ваши места сохранены. Попробуйте снова или откройте карту в новой вкладке.", retry: "Повторить", external: "Открыть карту", connection: "Часть карты не загрузилась", estimated: "Предложенные места · расстояния примерные", walking: "Пеший маршрут", active: "Навигация включена", start: "Точка старта", gps: "Вы здесь" },
  kk: { map: "Қаланың интерактивті картасы", zoomIn: "Жақындату", zoomOut: "Алыстату", recenter: "Орналасқан жеріңізге оралу", north: "Солтүстікке бағыттау", flat: "2D карта", depth: "3D карта", loading: "Қала картасы жүктелуде", unavailable: "Карта жүктелмеді", error: "Таңдалған орындар сақталды. Қайталап көріңіз немесе картаны жаңа бетте ашыңыз.", retry: "Қайталау", external: "Картаны ашу", connection: "Картаның кейбір бөліктері жүктелмеді", estimated: "Ұсынылған орындар · қашықтық шамамен", walking: "Жаяу бағыт", active: "Навигация қосылды", start: "Бастапқы нүкте", gps: "Сіз осындасыз" },
};

function duration() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 240;
}

function viewPadding(map: MapLibreMap, inset: number) {
  const { clientHeight: height, clientWidth: width } = map.getContainer();
  return { top: Math.min(115, height * 0.22), left: Math.min(65, width * 0.13), right: Math.min(110, width * 0.25), bottom: Math.min(inset + 45, height * 0.42) };
}

export function MapLibreCityMap({ location, result, language, onRoute, selectedId, onSelectPlace, onCatalogSelect, catalogSelection, navigation, navigating = false, userLocation, insetBottom = 200 }: CityMapProps) {
  const t = text[language];
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const latest = useRef({ location, onSelectPlace, onCatalogSelect, language });
  latest.current = { location, onSelectPlace, onCatalogSelect, language };
  const { catalog, status: catalogStatus, retry: retryCatalog } = usePlaceCatalog();
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [catalogCenter, setCatalogCenter] = useState({ lat: location.lat, lon: location.lon });
  const depthEnabled = useRef(true);
  const depthTarget = useRef<number | null>(null);
  const [is3D, setIs3D] = useState(true);
  const markers = useRef<Marker[]>([]);
  const gpsMarker = useRef<Marker | null>(null);
  const keyboardSelection = useRef(false);
  const [retry, setRetry] = useState(0);
  const [ready, setReady] = useState(0);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState(false);
  const [tileError, setTileError] = useState(false);
  const [bearing, setBearing] = useState(0);
  const places = useMemo(() => result?.recommendations ?? [], [result]);
  useMapControlsInset(container, insetBottom, places.length > 0);
  const lineCoordinates = useMemo(() => navigation?.geometry.coordinates ?? (places.length ? [[location.lon, location.lat], ...places.map((place) => [place.lon, place.lat])] as [number, number][] : []), [navigation, places, location.lat, location.lon]);
  const selectedTarget = useRef({ result, selectedId });

  useEffect(() => {
    if (!container.current) return;
    setLoading(true);
    setFailure(false);
    setTileError(false);
    setReady(0);
    let map: MapLibreMap;
    let disposed = false;
    let didLoad = false;
    let tileFailures = 0;
    let loadTimer: ReturnType<typeof setTimeout>;
    try {
      const initial = latest.current.location;
      map = new MapLibreMap({
        container: container.current,
        style: STYLE_URL,
        center: [initial.lon, initial.lat],
        zoom: 15.1,
        pitch: depthEnabled.current ? 48 : 0,
        bearing: -18,
        maxPitch: depthEnabled.current ? 60 : 0,
        minZoom: 3,
        maxZoom: 19,
        attributionControl: false,
        canvasContextAttributes: { antialias: true },
      });
      mapRef.current = map;
      map.addControl(new AttributionControl({ compact: false }), "bottom-right");
      map.getCanvas().setAttribute("aria-label", t.map);
      map.on("load", () => {
        if (disposed) return;
        didLoad = true;
        clearTimeout(loadTimer);
        try {
          prepareCityStyle(map, latest.current.language, depthEnabled.current);
          addCatalogLayers(map, latest.current.language);
          map.addSource("qala-route", { type: "geojson", data: EMPTY_LINE });
          map.addLayer({ id: "qala-route-casing", type: "line", source: "qala-route", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": "#ffffff", "line-width": 9, "line-opacity": 0.95 } });
          map.addLayer({ id: "qala-route-line", type: "line", source: "qala-route", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": "#3666f6", "line-width": 4.5 } });
          setLoading(false);
          setFailure(false);
          setTileError(tileFailures > 0);
          setReady((value) => value + 1);
        } catch {
          setLoading(false);
          setFailure(true);
        }
      });
      map.on("error", () => { if (!disposed) { tileFailures += 1; setTileError(true); } });
      map.on("click", event => {
        if (!map.getLayer(CATALOG_POINTS) || disposed) return;
        const hits = map.queryRenderedFeatures([[event.point.x - 11, event.point.y - 11], [event.point.x + 11, event.point.y + 11]], { layers: [CATALOG_CLUSTERS, CATALOG_POINTS] });
        const hit = hits.sort((a, b) => {
          if (a.geometry.type !== "Point" || b.geometry.type !== "Point") return 0;
          const pa = map.project(a.geometry.coordinates as [number, number]);
          const pb = map.project(b.geometry.coordinates as [number, number]);
          return Math.hypot(pa.x - event.point.x, pa.y - event.point.y) - Math.hypot(pb.x - event.point.x, pb.y - event.point.y);
        })[0];
        if (!hit || hit.geometry.type !== "Point") return;
        const coordinates = hit.geometry.coordinates as [number, number];
        if (hit.properties.cluster) {
          const source = map.getSource(CATALOG_SOURCE) as GeoJSONSource;
          void source.getClusterExpansionZoom(Number(hit.properties.cluster_id)).then(zoom => {
            if (!disposed) map.easeTo({ center: coordinates, zoom: Math.min(zoom, 19), duration: duration() });
          }).catch(() => { if (!disposed) setCatalogOpen(true); });
        } else {
          latest.current.onCatalogSelect?.(catalogPlace(hit as unknown as CatalogFeature, latest.current.language));
        }
      });
      map.on("mousemove", event => {
        if (!map.getLayer(CATALOG_POINTS)) return;
        map.getCanvas().style.cursor = map.queryRenderedFeatures(event.point, { layers: [CATALOG_CLUSTERS, CATALOG_POINTS] }).length ? "pointer" : "";
      });
      map.on("moveend", () => {
        if (disposed) return;
        setBearing(map.getBearing());
        const center = map.getCenter();
        setCatalogCenter({ lat: center.lat, lon: center.lng });
        if (depthTarget.current !== null && Math.abs(map.getPitch() - depthTarget.current) < 0.1) depthTarget.current = null;
      });
      // A direct gesture owns the camera immediately, including when it
      // interrupts the short 3D transition. Programmatic follows keep its target.
      for (const event of ["dragstart", "rotatestart", "pitchstart", "zoomstart"] as const) {
        map.on(event, (movement) => { if (movement.originalEvent) depthTarget.current = null; });
      }
      map.on("webglcontextlost", () => { if (!disposed) { setFailure(true); setLoading(false); } });
      loadTimer = setTimeout(() => { if (!disposed && !didLoad) { setFailure(true); setLoading(false); } }, 16000);
    } catch {
      mapRef.current?.remove();
      mapRef.current = null;
      setLoading(false);
      setFailure(true);
      return;
    }
    const observer = new ResizeObserver(() => map.resize());
    observer.observe(container.current);
    return () => {
      disposed = true;
      clearTimeout(loadTimer);
      observer.disconnect();
      markers.current.forEach((marker) => marker.remove());
      markers.current = [];
      gpsMarker.current?.remove();
      gpsMarker.current = null;
      map.remove();
      mapRef.current = null;
      depthTarget.current = null;
    };
    // Recreate only on explicit retry; live data updates use sources.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [retry]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    setCityMapLanguage(map, language);
    map.getCanvas().setAttribute("aria-label", t.map);
  }, [language, ready, t.map]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource(CATALOG_SOURCE) as GeoJSONSource | undefined)?.setData(catalog);
    map.setLayoutProperty("qala-catalog-names", "text-field", ["coalesce", ["get", `name_${language}`], ["get", "name"]]);
  }, [catalog, language, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    // Route markers and the focused venue already carry their own labels.
    // Suppress duplicate text only; every point stays in the map source.
    const labeled = [...places.map(place => place.id), ...(catalogSelection ? [catalogSelection.id] : [])];
    map.setFilter("qala-catalog-names", ["all", ["!", ["has", "point_count"]], ["!", ["in", ["get", "id"], ["literal", labeled]]]]);
  }, [places, catalogSelection, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource("qala-catalog-selected") as GeoJSONSource | undefined)?.setData(selectedCatalogData(catalogSelection));
    if (catalogSelection) {
      map.stop();
      map.easeTo({ center: [catalogSelection.lon, catalogSelection.lat], zoom: Math.max(map.getZoom(), 17), pitch: cameraPitch(), padding: viewPadding(map, insetBottom), duration: document.documentElement.dataset.input === "keyboard" ? 0 : duration() });
    }
  }, [catalogSelection, ready, insetBottom]);

  // A route fit or GPS update can interrupt the opening transition. Retain its
  // intended pitch until reached; afterwards preserve the user's own tilt.
  function cameraPitch() {
    return depthEnabled.current ? depthTarget.current ?? mapRef.current?.getPitch() ?? 48 : 0;
  }

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const source = map.getSource("qala-route") as GeoJSONSource | undefined;
    source?.setData(lineCoordinates.length > 1 ? { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: lineCoordinates } } : EMPTY_LINE);
    map.setPaintProperty("qala-route-line", "line-dasharray", navigation ? [1, 0] : [1, 2]);
    map.setPaintProperty("qala-route-line", "line-opacity", navigation ? 1 : 0.65);
  }, [lineCoordinates, navigation, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    markers.current.forEach((marker) => marker.remove());
    const next: Marker[] = [];
    const origin = document.createElement("div");
    origin.className = "citymap-origin";
    origin.title = `${t.start}: ${location.label}`;
    origin.setAttribute("role", "img");
    origin.setAttribute("aria-label", origin.title);
    origin.appendChild(document.createElement("span"));
    next.push(new Marker({ element: origin }).setLngLat([location.lon, location.lat]).addTo(map));
    places.forEach((place, index) => {
      const element = document.createElement("div");
      element.className = "citymap-place-anchor";
      element.dataset.placeId = place.id;
      const button = document.createElement("button");
      button.type = "button";
      button.className = `citymap-place-marker${place.id === selectedId ? " is-selected" : ""}`;
      button.setAttribute("aria-label", `${index + 1}. ${place.name}`);
      button.setAttribute("aria-pressed", String(place.id === selectedId));
      button.textContent = String(index + 1);
      button.addEventListener("click", (event) => { event.stopPropagation(); keyboardSelection.current = event.detail === 0; latest.current.onSelectPlace?.(place.id); });
      element.appendChild(button);
      if (place.id === selectedId) {
        const label = document.createElement("span");
        label.className = "citymap-place-label";
        label.textContent = place.name;
        element.appendChild(label);
      }
      next.push(new Marker({ element, anchor: "center" }).setLngLat([place.lon, place.lat]).addTo(map));
    });
    markers.current = next;
    return () => next.forEach((marker) => marker.remove());
  }, [location, places, ready, t]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    if (!userLocation) {
      gpsMarker.current?.remove();
      gpsMarker.current = null;
      return;
    }
    // GPS fixes must not rebuild place buttons or discard keyboard focus.
    // The map lifecycle owns this marker's cleanup on retry and unmount.
    if (!gpsMarker.current) {
      const element = document.createElement("div");
      element.className = "citymap-gps";
      element.setAttribute("role", "img");
      element.appendChild(document.createElement("span"));
      gpsMarker.current = new Marker({ element }).setLngLat([userLocation.lon, userLocation.lat]).addTo(map);
    }
    const marker = gpsMarker.current;
    const element = marker.getElement();
    element.title = t.gps;
    element.setAttribute("aria-label", t.gps);
    marker.setLngLat([userLocation.lon, userLocation.lat]);
    let heading = element.querySelector("i");
    if (typeof userLocation.heading === "number") {
      if (!heading) { heading = document.createElement("i"); element.appendChild(heading); }
      heading.style.transform = `rotate(${userLocation.heading}deg)`;
    } else {
      heading?.remove();
    }
  }, [userLocation, ready, t.gps]);

  useEffect(() => {
    markers.current.forEach((marker) => {
      const element = marker.getElement();
      if (!element.dataset.placeId) return;
      const selected = element.dataset.placeId === selectedId;
      const button = element.querySelector("button");
      button?.classList.toggle("is-selected", selected);
      button?.setAttribute("aria-pressed", String(selected));
      element.querySelector(".citymap-place-label")?.remove();
      const place = places.find((candidate) => candidate.id === element.dataset.placeId);
      if (selected && place) {
        const label = document.createElement("span");
        label.className = "citymap-place-label";
        label.textContent = place.name;
        element.appendChild(label);
      }
    });
  }, [selectedId, places, ready, t]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    map.stop();
    const points: [number, number][] = lineCoordinates.length > 1 ? lineCoordinates : [[location.lon, location.lat]];
    if (points.length > 1) {
      const bounds = points.reduce((box, point) => box.extend(point), new LngLatBounds(points[0], points[0]));
      // v6 otherwise adds this inset to padding retained by selected-place
      // camera moves, shrinking a nearby route into a city-wide view.
      map.fitBounds(bounds, { padding: viewPadding(map, insetBottom), absolutePadding: true, maxZoom: 16.5, pitch: cameraPitch(), bearing: map.getBearing(), duration: duration(), linear: true, essential: false });
    } else {
      map.easeTo({ center: [location.lon, location.lat], zoom: 15.1, pitch: cameraPitch(), padding: viewPadding(map, insetBottom), duration: duration() });
    }
  }, [location.lat, location.lon, lineCoordinates, ready, insetBottom]);

  useEffect(() => {
    const previous = selectedTarget.current;
    selectedTarget.current = { result, selectedId };
    const map = mapRef.current;
    if (!map || !ready || result !== previous.result || selectedId === previous.selectedId) return;
    const place = places.find((candidate) => candidate.id === selectedId);
    if (!place) return;
    map.stop();
    map.easeTo({ center: [place.lon, place.lat], zoom: Math.max(map.getZoom(), 16), pitch: cameraPitch(), padding: viewPadding(map, insetBottom), duration: keyboardSelection.current ? 0 : duration() });
    keyboardSelection.current = false;
  }, [selectedId, places, result, ready, insetBottom]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !navigating || !userLocation) return;
    map.stop();
    map.easeTo({ center: [userLocation.lon, userLocation.lat], zoom: 17, pitch: cameraPitch(), bearing: userLocation.heading ?? map.getBearing(), padding: viewPadding(map, insetBottom), duration: duration() });
  }, [userLocation, navigating, ready, insetBottom]);

  function changeCamera(action: "in" | "out" | "north" | "locate" | "depth", keyboard: boolean) {
    const map = mapRef.current;
    if (!map || !ready || failure) return;
    map.stop();
    const time = keyboard ? 0 : duration();
    if (action === "depth") {
      const enabled = !depthEnabled.current;
      depthEnabled.current = enabled;
      depthTarget.current = enabled ? 48 : null;
      setIs3D(enabled);
      setCityMapDepth(map, enabled);
      map.setMaxPitch(enabled ? 60 : 0);
      if (enabled) map.easeTo({ pitch: 48, duration: time });
      else map.setPitch(0);
      return;
    }
    const pitch = cameraPitch();
    if (action === "in" || action === "out") map.easeTo({ zoom: map.getZoom() + (action === "in" ? 1 : -1), pitch, duration: time });
    if (action === "north") map.easeTo({ bearing: 0, pitch, duration: time });
    if (action === "locate") map.easeTo({ center: [userLocation?.lon ?? location.lon, userLocation?.lat ?? location.lat], zoom: 16, pitch, padding: viewPadding(map, insetBottom), duration: time });
  }

  const externalMap = `https://www.openstreetmap.org/?mlat=${location.lat}&mlon=${location.lon}#map=16/${location.lat}/${location.lon}`;
  // Map canvases form a stacking context beneath the itinerary overlays.
  // Put actionable recovery/help in their common parent so cards cannot cover it.
  const overlayHost = container.current?.closest(".map-stage") ?? container.current?.parentElement;
  return (
    <section className="citymap-scene" data-map-provider="openfreemap" data-map-depth={is3D ? "3d" : "2d"} aria-label={t.map} style={{ "--citymap-inset": `${insetBottom}px` } as CSSProperties}>
      <div ref={container} className="citymap-renderer" />
      <div className="citymap-vignette" aria-hidden="true" />
      {loading && !failure && <div className="citymap-loading" role="status"><span className="citymap-loading-dot" />{t.loading}</div>}
      {failure && overlayHost && createPortal(<div className="citymap-fallback" role="alert">
        <span className="citymap-fallback-icon"><WifiSlash size={25} /></span>
        <h2>{t.unavailable}</h2>
        <p>{t.error}</p>
        <div><button type="button" onClick={() => setRetry((value) => value + 1)}><ArrowClockwise size={17} />{t.retry}</button><a href={externalMap} target="_blank" rel="noreferrer">{t.external}<ArrowSquareOut size={16} /></a></div>
      </div>, overlayHost)}
      {tileError && !failure && !loading && <div className="citymap-network" role="status"><WifiSlash size={15} /><span>{t.connection}</span><button type="button" aria-label={t.retry} onClick={() => setRetry((value) => value + 1)}><ArrowClockwise size={15} /></button><a href={externalMap} target="_blank" rel="noreferrer" aria-label={t.external}><ArrowSquareOut size={15} /></a></div>}
      <div className="citymap-controls" aria-label={language === "en" ? "Map controls" : language === "ru" ? "Управление картой" : "Картаны басқару"}>
        <div className="citymap-control-group">
          <button type="button" aria-label={t.zoomIn} title={t.zoomIn} onClick={(event) => changeCamera("in", event.detail === 0)} disabled={failure || !ready}><Plus size={19} weight="bold" /></button>
          <button type="button" aria-label={t.zoomOut} title={t.zoomOut} onClick={(event) => changeCamera("out", event.detail === 0)} disabled={failure || !ready}><Minus size={19} weight="bold" /></button>
        </div>
        <div className="citymap-control-group">
          <button type="button" aria-label={t.north} title={t.north} onClick={(event) => changeCamera("north", event.detail === 0)} disabled={failure || !ready}><Compass size={22} weight="duotone" style={{ transform: `rotate(${-bearing}deg)` }} /></button>
          <button type="button" className={is3D ? "is-active" : undefined} aria-label={is3D ? t.flat : t.depth} aria-pressed={is3D} title={is3D ? t.flat : t.depth} onClick={(event) => changeCamera("depth", event.detail === 0)} disabled={failure || !ready}>{is3D ? "3D" : "2D"}</button>
        </div>
        <div className="citymap-control-group citymap-quick-controls"><button type="button" aria-label={language === "ru" ? "Места на карте" : language === "kk" ? "Картадағы орындар" : "Places on the map"} title={language === "ru" ? "Места на карте" : language === "kk" ? "Картадағы орындар" : "Places on the map"} onClick={() => setCatalogOpen(true)}>{catalogStatus === "loading" ? <CircleNotch size={21} className="animate-spin" /> : catalogStatus === "error" ? <WifiSlash size={21} /> : <MapPin size={21} weight="duotone" />}</button><button type="button" aria-label={t.recenter} title={t.recenter} onClick={(event) => changeCamera("locate", event.detail === 0)} disabled={failure || !ready}><Crosshair size={21} weight="bold" /></button></div>
        {places.length > 0 && <div className="citymap-control-group"><button type="button" aria-label="Walking itinerary" title="Walking itinerary" onClick={onRoute}><Footprints size={20} /></button></div>}
      </div>
      <PlaceCatalogBrowser open={catalogOpen} onOpenChange={setCatalogOpen} catalog={catalog} status={catalogStatus} onRetry={retryCatalog} language={language} center={catalogCenter} onSelect={place => latest.current.onCatalogSelect?.(place)} />
    </section>
  );
}
