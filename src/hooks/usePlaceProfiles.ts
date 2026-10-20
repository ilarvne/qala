import { useCallback, useEffect, useRef, useState } from "react";
import { readApiJson } from "@/lib/api";
import { decodeTwoGISResponse, type TwoGISResponse } from "@/lib/twogis-api";
import type { Language } from "@/types";

export type PlaceProfileState = {
  status: "loading" | "ready" | "error";
  result: TwoGISResponse | null;
  error: "failed" | "timeout" | null;
};
export type PlaceProfileLoadOptions = { signal?: AbortSignal; force?: boolean };
type Profiles = Readonly<Record<string, PlaceProfileState>>;
type Batch = { signature: string; controller: AbortController; completion: Promise<void> | null };

/** Explicitly load at most three currently displayed places; never fetch on mount.
 *
 * The state belongs only to the active view. It never enters Place objects,
 * planner responses, browser storage or a query cache. New plans must call
 * clear() before load(); repeated consumers of the same current IDs reuse the
 * visible state. force is reserved for an explicit refresh/retry action.
 */
export function usePlaceProfiles(language: Language) {
  const [state, setState] = useState<{ language: Language; profiles: Profiles }>({ language, profiles: {} });
  const mounted = useRef(true);
  const revision = useRef(0);
  const current = useRef<Batch | null>(null);
  const displayed = useRef("");
  const languageRef = useRef(language);
  languageRef.current = language;

  const clear = useCallback(() => {
    revision.current += 1;
    current.current?.controller.abort();
    current.current = null;
    displayed.current = "";
    if (mounted.current) setState({ language: languageRef.current, profiles: {} });
  }, []);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; clear(); };
  }, [clear]);
  useEffect(() => { clear(); }, [language, clear]);

  const load = useCallback(async (requestedIds: readonly string[], options: PlaceProfileLoadOptions = {}): Promise<void> => {
    if (!mounted.current || options.signal?.aborted) return;
    const ids = [...new Set(requestedIds.filter(id => typeof id === "string" && /^[A-Za-z0-9][A-Za-z0-9_-]{0,199}$/.test(id)))].slice(0, 3);
    const signature = `${language}/${[...ids].sort().join(",")}`;
    if (!options.force && displayed.current === signature) {
      await current.current?.completion;
      return;
    }
    clear();
    if (!ids.length) return;
    const token = revision.current;
    const controller = new AbortController();
    const batch: Batch = { signature, controller, completion: null };
    current.current = batch;
    displayed.current = signature;
    const live = () => mounted.current && revision.current === token && languageRef.current === language && !controller.signal.aborted;
    const update = (id: string, value: PlaceProfileState) => {
      if (!live()) return;
      setState(previous => previous.language === language && live()
        ? { language, profiles: { ...previous.profiles, [id]: value } }
        : previous);
    };
    setState({ language, profiles: Object.fromEntries(ids.map(id => [id, { status: "loading", result: null, error: null } satisfies PlaceProfileState])) });
    const externalAbort = () => { if (current.current === batch) clear(); };
    options.signal?.addEventListener("abort", externalAbort, { once: true });
    let next = 0;
    const worker = async () => {
      while (live() && next < ids.length) {
        const id = ids[next++];
        const request = new AbortController();
        let timedOut = false;
        const abort = () => request.abort();
        controller.signal.addEventListener("abort", abort, { once: true });
        const timeout = window.setTimeout(() => { timedOut = true; request.abort(); }, 20_000);
        try {
          const response = await fetch(`/api/pois/${encodeURIComponent(id)}/sources/2gis?language=${language}`, {
            signal: request.signal, cache: "no-store",
          });
          const result = decodeTwoGISResponse(await readApiJson<unknown>(response, "Place profile unavailable"));
          if (!request.signal.aborted) update(id, { status: "ready", result, error: null });
        } catch {
          if (live()) update(id, { status: "error", result: null, error: timedOut ? "timeout" : "failed" });
        } finally {
          window.clearTimeout(timeout);
          controller.signal.removeEventListener("abort", abort);
        }
      }
    };
    batch.completion = Promise.all(Array.from({ length: Math.min(2, ids.length) }, worker)).then(() => undefined);
    try {
      await batch.completion;
    } finally {
      options.signal?.removeEventListener("abort", externalAbort);
      if (current.current === batch) current.current = null;
    }
  }, [language, clear]);

  const profiles = state.language === language ? state.profiles : {};
  return { profiles, pending: Object.values(profiles).some(profile => profile.status === "loading"), load, clear };
}
