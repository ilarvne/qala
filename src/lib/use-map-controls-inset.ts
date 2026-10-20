import { useEffect, type RefObject } from "react";

/** Keep map controls above the actual itinerary, including responsive notices. */
export function useMapControlsInset(container: RefObject<HTMLDivElement | null>, fallback: number, hasPlaces: boolean) {
  useEffect(() => {
    const renderer = container.current;
    const stage = renderer?.closest<HTMLElement>(".map-stage");
    if (!renderer || !stage) return;
    const cards = stage.querySelector<HTMLElement>(".map-bottom");
    const update = () => {
      const bottom = cards ? stage.getBoundingClientRect().bottom - cards.getBoundingClientRect().top + 12 : fallback + 12;
      renderer.parentElement?.style.setProperty("--citymap-controls-bottom", `${Math.max(12, bottom)}px`);
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(stage);
    if (cards) observer.observe(cards);
    return () => observer.disconnect();
  }, [container, fallback, hasPlaces]);
}
