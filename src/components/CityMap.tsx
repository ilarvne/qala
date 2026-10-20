import { Component, Suspense, lazy, type ReactNode } from "react";
import { ArrowClockwise } from "@phosphor-icons/react";
import type { CityMapProps } from "@/components/map-types";
import "@/styles/map.css";

export type { CityMapProps, StreetRoute } from "@/components/map-types";

const MapLibreCityMap = lazy(() => import("@/components/MapLibreCityMap").then(module => ({ default: module.MapLibreCityMap })));

class MapLoadBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (!this.state.failed) return this.props.children;
    return <section className="citymap-scene citymap-module-error" aria-label="Map unavailable">
      <div className="citymap-fallback" role="alert">
        <h2>The map couldn’t load</h2>
        <div>
          <button type="button" onClick={() => window.location.reload()}><ArrowClockwise size={16} />Reload page</button>
        </div>
      </div>
    </section>;
  }
}

export function CityMap(props: CityMapProps) {
  return <MapLoadBoundary>
    <Suspense fallback={<section className="citymap-scene" aria-busy="true"><div className="citymap-loading" role="status"><span className="citymap-loading-dot" />{props.language === "ru" ? "Загружаем карту" : props.language === "kk" ? "Карта жүктелуде" : "Loading map"}</div></section>}>
      <MapLibreCityMap {...props} />
    </Suspense>
  </MapLoadBoundary>;
}
