import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { readApiJson } from "@/lib/api";
import { conversationWithControls, effectivePlannerContext, planningContextKey, samePlannerOrigin } from "@/lib/planner-context";
import type { Language, Location, Recommendation } from "@/types";

export interface PlannerSettings {
  location: Location;
  language: Language;
  duration: number;
  group: number;
  accessible: boolean;
  indoor: boolean;
  plannedTime: string;
  airportTransfer: number | null;
}
export interface MemoryPreferences {
  interests?: string[]; language?: Language; duration_minutes?: number; indoor?: boolean;
  accessible?: boolean; retention_days?: number; excluded_categories?: string[]; max_walk_minutes?: number | null;
}
interface MemoryResponse { preferences?: MemoryPreferences | null; generation?: number }
export const initialSettings: PlannerSettings = {
  location: { lat: 51.1282882, lon: 71.4304546, label: "Bayterek · Nurzhol Boulevard" },
  language: "en", duration: 60, group: 1, accessible: false, indoor: false,
  plannedTime: "14:00", airportTransfer: null,
};
export const initialQuery = "Plan an interesting architecture walk near Bayterek, with a coffee stop if there is time.";
const MEMORY_CAPABILITY = "qala-memory-session";
const REVOKED_CAPABILITY = "qala-memory-revoked";
const validCapability = (value: string | null): value is string => Boolean(value && /^[A-Za-z0-9_-]{16,128}$/.test(value));
const controlMessage = (language: Language) => ({ en: "Recommend nearby places using the selected preferences.", ru: "Подбери места рядом с учетом выбранных настроек.", kk: "Таңдалған параметрлерге сай жақын жерлерді ұсын." })[language];

function session() {
  let persistent: string | null = null, temporary: string | null = null;
  try { persistent = localStorage.getItem(MEMORY_CAPABILITY); } catch { /* Storage may be unavailable in private contexts. */ }
  try { temporary = sessionStorage.getItem("qala-session"); } catch { /* An in-memory capability still supports this visit. */ }
  const value = validCapability(persistent) ? persistent : validCapability(temporary) ? temporary : crypto.randomUUID();
  try { sessionStorage.setItem("qala-session", value); } catch { /* Keep the capability in React state. */ }
  return value;
}

function persistCapability(sessionId: string, enabled: boolean) {
  try {
    if (enabled) { localStorage.setItem(MEMORY_CAPABILITY, sessionId); sessionStorage.removeItem(REVOKED_CAPABILITY); }
    else if (localStorage.getItem(MEMORY_CAPABILITY) === sessionId) localStorage.removeItem(MEMORY_CAPABILITY);
  } catch { /* Persistence is optional; no chat or coordinates are stored here. */ }
}

function revokeCapability(sessionId: string) {
  persistCapability(sessionId, false);
  try { sessionStorage.setItem(REVOKED_CAPABILITY, sessionId); } catch { /* The in-memory intent still prevents re-enabling. */ }
}

function wasRevoked(sessionId: string) {
  try { return sessionStorage.getItem(REVOKED_CAPABILITY) === sessionId; } catch { return false; }
}

export function plannerBody(settings: PlannerSettings, sessionId: string, remember: boolean, generation = 0, useSavedPreferences = remember) {
  return {
    location: settings.location, duration_minutes: settings.duration,
    language: settings.language, group_size: settings.group,
    accessible: settings.accessible, indoor: settings.indoor,
    airport_transfer_minutes: settings.airportTransfer, interests: [],
    starts_at: settings.plannedTime === "now" ? undefined :
      new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Almaty" }) + "T" + settings.plannedTime + ":00+05:00",
    session_id: sessionId, remember, memory_generation: generation, use_saved_preferences: useSavedPreferences,
  };
}

function rememberedSettings(settings: PlannerSettings, preferences: MemoryPreferences): PlannerSettings {
  return { ...settings,
    language: ["en", "ru", "kk"].includes(preferences.language ?? "") ? preferences.language! : settings.language,
    duration: Number.isInteger(preferences.duration_minutes) && preferences.duration_minutes! >= 10 && preferences.duration_minutes! <= 480 ? preferences.duration_minutes! : settings.duration,
    indoor: typeof preferences.indoor === "boolean" ? preferences.indoor : settings.indoor,
    accessible: typeof preferences.accessible === "boolean" ? preferences.accessible : settings.accessible,
  };
}

export function usePlanner() {
  const [settings, setSettings] = useState<PlannerSettings>(initialSettings);
  const [result, setResult] = useState<Recommendation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [remember, setRemember] = useState(false);
  const [memoryBusy, setMemoryBusy] = useState(false);
  const [memoryPreferences, setMemoryPreferences] = useState<MemoryPreferences | null>(null);
  const [memoryGeneration, setMemoryGeneration] = useState(0);
  const [sessionId] = useState(session);
  const [lastQuery, setLastQuery] = useState(initialQuery);
  const [resultContext, setResultContext] = useState<Record<string, unknown> | null>(null);
  const interactionRevision = useRef(0);
  const memoryIntentRevision = useRef(0);
  const memoryReadRevision = useRef(0);
  const memoryIntent = useRef<"unknown" | "enabled" | "revoked">(wasRevoked(sessionId) ? "revoked" : "unknown");
  const memoryQueue = useRef<Promise<void>>(Promise.resolve());
  const memoryPending = useRef(0);
  const generationRef = useRef(0);
  const rememberRef = useRef(false);
  const mounted = useRef(true);
  const request = useRef<AbortController | null>(null);
  const settingsRef = useRef(settings);
  const resultRef = useRef(result);
  const resultContextRef = useRef(resultContext);
  settingsRef.current = settings; resultRef.current = result; resultContextRef.current = resultContext;
  const context = useMemo(() => plannerBody(settings, sessionId, remember, memoryGeneration), [settings, sessionId, remember, memoryGeneration]);
  const contextRef = useRef<Record<string, unknown>>(context);
  contextRef.current = context;

  const consent = (value: boolean) => {
    rememberRef.current = value;
    contextRef.current = { ...contextRef.current, remember: value, use_saved_preferences: value };
    if (mounted.current) setRemember(value);
  };
  const observeGeneration = (value: unknown) => {
    if (!Number.isInteger(value) || Number(value) < generationRef.current) return;
    generationRef.current = Number(value);
    contextRef.current = { ...contextRef.current, memory_generation: Number(value) };
    if (mounted.current) setMemoryGeneration(Number(value));
  };
  const applyResult = (data: Recommendation, captured: Record<string, unknown>) => {
    const currentConsentEpoch = Number(data.context.memory_generation) >= generationRef.current;
    observeGeneration(data.context.memory_generation);
    if (currentConsentEpoch && data.context.memory_revoked_during_request === true) {
      memoryIntent.current = "revoked"; consent(false); revokeCapability(sessionId); setMemoryPreferences(null);
    }
    const effective: Record<string, unknown> = { ...effectivePlannerContext(captured, data), remember: rememberRef.current, memory_generation: generationRef.current };
    const next = { ...settingsRef.current, duration: Number(effective.duration_minutes), group: Number(effective.group_size),
      indoor: Boolean(effective.indoor), accessible: Boolean(effective.accessible),
      airportTransfer: typeof effective.airport_transfer_minutes === "number" ? effective.airport_transfer_minutes : null };
    settingsRef.current = next; contextRef.current = effective; resultRef.current = data; resultContextRef.current = effective;
    setSettings(next); setResult(data); setResultContext(effective);
  };

  const plan = useCallback(async (text: string, override?: PlannerSettings, persist?: boolean, startupInterests?: string[]) => {
    interactionRevision.current += 1;
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setLoading(true); setError(""); setLastQuery(text);
    const body = override ? plannerBody(override, sessionId, persist ?? rememberRef.current, generationRef.current, rememberRef.current) :
      { ...contextRef.current, remember: persist ?? rememberRef.current, memory_generation: generationRef.current, use_saved_preferences: rememberRef.current };
    const previous = resultRef.current?.conversation;
    const conversation = previous && samePlannerOrigin(resultContextRef.current, body) ? conversationWithControls(previous, body) : undefined;
    try {
      const response = await fetch("/api/recommend", {
        method: "POST", signal: controller.signal, headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...body, message: text, conversation, ...(startupInterests ? { interests: startupInterests } : {}) }),
      });
      const data = await readApiJson<Recommendation>(response, "The city guide is unavailable. Try again.");
      if (!controller.signal.aborted && mounted.current && planningContextKey(body) === planningContextKey(contextRef.current)) applyResult(data, body);
      return data;
    } catch (reason) {
      if (controller.signal.aborted || !mounted.current) return;
      setError(reason instanceof TypeError ? "Connection lost. Check your connection and try again." :
        reason instanceof Error ? reason.message : "The city guide is unavailable. Try again.");
    } finally { if (!controller.signal.aborted && mounted.current) setLoading(false); }
  }, [sessionId]);

  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    const readRevision = ++memoryReadRevision.current, intent = memoryIntentRevision.current;
    void (async () => {
      let preferences: MemoryPreferences | null = null;
      try {
        const response = await fetch("/api/memory/" + sessionId, { signal: controller.signal, cache: "no-store" });
        const data = await readApiJson<MemoryResponse>(response, "Preferences could not be checked.");
        if (controller.signal.aborted || !mounted.current) return;
        const fresh = !Number.isInteger(data.generation) || Number(data.generation) >= generationRef.current;
        observeGeneration(data.generation);
        if (fresh && readRevision === memoryReadRevision.current && intent === memoryIntentRevision.current) {
          const stored = data.preferences ?? null;
          setMemoryPreferences(stored);
          if (memoryIntent.current !== "revoked") { preferences = stored; consent(Boolean(stored)); }
          if (!stored) persistCapability(sessionId, false);
        }
      } catch { /* Preference availability never prevents city discovery. */ }
      if (!controller.signal.aborted && mounted.current && interactionRevision.current === 0) {
        const next = preferences ? rememberedSettings(settingsRef.current, preferences) : settingsRef.current;
        settingsRef.current = next; setSettings(next);
        contextRef.current = plannerBody(next, sessionId, rememberRef.current, generationRef.current);
        await plan(preferences ? controlMessage(next.language) : initialQuery, next, false, preferences?.interests);
      }
    })();
    return () => { mounted.current = false; controller.abort(); request.current?.abort(); };
  }, [sessionId]);

  useEffect(() => {
    const changed = (event: StorageEvent) => {
      if (event.key !== MEMORY_CAPABILITY || event.oldValue !== sessionId || event.newValue === sessionId) return;
      memoryIntentRevision.current += 1; memoryReadRevision.current += 1;
      memoryIntent.current = "revoked"; consent(false); revokeCapability(sessionId); setMemoryPreferences(null);
    };
    window.addEventListener("storage", changed);
    return () => window.removeEventListener("storage", changed);
  }, [sessionId]);
  useEffect(() => { document.documentElement.lang = settings.language; }, [settings.language]);

  const update = (patch: Partial<PlannerSettings>, refresh = true) => {
    interactionRevision.current += 1;
    const next = { ...settingsRef.current, ...patch };
    settingsRef.current = next; contextRef.current = plannerBody(next, sessionId, rememberRef.current, generationRef.current); setSettings(next);
    if (refresh) void plan(controlMessage(next.language), next);
    else { request.current?.abort(); setLoading(false); }
    return next;
  };
  const acceptResult = (data: Recommendation, requestContext?: Record<string, unknown>) => {
    if (requestContext && planningContextKey(requestContext) !== planningContextKey(contextRef.current)) return;
    applyResult(data, requestContext ?? contextRef.current);
    request.current?.abort(); setLoading(false); setError("");
  };

  const inspectMemory = async () => {
    if (memoryPending.current) return;
    const readRevision = ++memoryReadRevision.current, intent = memoryIntentRevision.current;
    const response = await fetch("/api/memory/" + sessionId, { cache: "no-store" });
    const data = await readApiJson<MemoryResponse>(response, "Preferences could not be checked.");
    const fresh = !Number.isInteger(data.generation) || Number(data.generation) >= generationRef.current;
    observeGeneration(data.generation);
    if (!mounted.current || !fresh || memoryPending.current || readRevision !== memoryReadRevision.current || intent !== memoryIntentRevision.current) return;
    setMemoryPreferences(data.preferences ?? null);
    if (memoryIntent.current !== "revoked") consent(Boolean(data.preferences));
    if (!data.preferences) persistCapability(sessionId, false);
  };

  const mutateMemory = (write: (revision: number) => Promise<void>) => {
    interactionRevision.current += 1;
    const revision = ++memoryIntentRevision.current;
    memoryReadRevision.current += 1; memoryPending.current += 1; setMemoryBusy(true);
    const operation = memoryQueue.current.then(() => write(revision));
    memoryQueue.current = operation.catch(() => undefined);
    return operation.finally(() => {
      memoryPending.current -= 1;
      if (mounted.current && memoryPending.current === 0) setMemoryBusy(false);
    });
  };
  const saveMemory = async (revision: number, preferences: Record<string, unknown>, intendedGeneration: number) => {
    const response = await fetch("/api/memory/" + sessionId, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ consent: true, ...preferences, memory_generation: intendedGeneration }) });
    if (response.status === 409) {
      if (revision === memoryIntentRevision.current) consent(false);
      const refresh = await fetch("/api/memory/" + sessionId, { cache: "no-store" });
      const current = await readApiJson<MemoryResponse>(refresh, "Preferences changed. Try again.");
      observeGeneration(current.generation);
      throw new Error("Preferences changed in another request. Check memory and try again.");
    }
    const data = await readApiJson<MemoryResponse>(response, "Preferences could not be saved. Try again.");
    observeGeneration(data.generation);
    if (!mounted.current || revision !== memoryIntentRevision.current) return;
    setMemoryPreferences(data.preferences ?? null); consent(Boolean(data.preferences)); persistCapability(sessionId, Boolean(data.preferences));
  };
  const changeRemember = (value: boolean) => {
    memoryIntent.current = value ? "enabled" : "revoked";
    const intendedGeneration = generationRef.current;
    if (!value) { consent(false); revokeCapability(sessionId); setMemoryPreferences(null); }
    const current = settingsRef.current, conversation = resultRef.current?.conversation;
    return mutateMemory(async (revision) => {
      if (value) {
        await saveMemory(revision, { interests: conversation?.interests ?? [], language: current.language,
          duration_minutes: current.duration, indoor: current.indoor, accessible: current.accessible,
          excluded_categories: conversation?.excluded_categories ?? [], max_walk_minutes: conversation?.max_walk_minutes ?? null }, intendedGeneration);
      } else {
        const response = await fetch("/api/memory/" + sessionId, { method: "DELETE" });
        const data = await readApiJson<MemoryResponse>(response, "Preferences could not be deleted. Try again.");
        observeGeneration(data.generation);
        if (mounted.current && revision === memoryIntentRevision.current) { setMemoryPreferences(null); consent(false); }
      }
    });
  };
  const editMemory = (interests: string[]) => {
    memoryIntent.current = "enabled";
    const intendedGeneration = generationRef.current, chosen = [...interests];
    return mutateMemory(revision => saveMemory(revision, { interests: chosen }, intendedGeneration));
  };

  const current = Boolean(result && planningContextKey(resultContext) === planningContextKey(context));
  const noteQuery = (text: string) => {
    interactionRevision.current += 1; request.current?.abort(); setLoading(false); setLastQuery(text);
  };
  return { settings, update, result, loading, error, plan, context, acceptResult, current,
    remember, memoryBusy, memoryPreferences, inspectMemory, editMemory, changeRemember, lastQuery, setLastQuery: noteQuery, setResult };
}
