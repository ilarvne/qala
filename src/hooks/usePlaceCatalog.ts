import { useEffect, useState } from "react";
import { readApiJson } from "@/lib/api";
import { EMPTY_CATALOG, type PlaceCatalog } from "@/lib/place-catalog";

export function usePlaceCatalog() {
  const [catalog, setCatalog] = useState<PlaceCatalog>(EMPTY_CATALOG);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setStatus("loading");
    void fetch("/api/pois/map", { signal: controller.signal })
      .then(response => readApiJson<PlaceCatalog>(response, "Place catalogue unavailable"))
      .then(data => {
        if (data.type !== "FeatureCollection" || !Array.isArray(data.features)) throw new Error("Invalid catalogue");
        if (!controller.signal.aborted) { setCatalog(data); setStatus("ready"); }
      }).catch(() => { if (!controller.signal.aborted) setStatus("error"); });
    return () => controller.abort();
  }, [revision]);
  return { catalog, status, retry: () => setRevision(value => value + 1) };
}
