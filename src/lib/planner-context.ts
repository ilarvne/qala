import type { ConversationContext, Recommendation } from "@/types";

function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => [key, canonical(item)]));
  return value;
}

/** Consent bookkeeping changes neither the route nor the planning constraints. */
export function planningContextKey(value: Record<string, unknown> | null): string {
  if (!value) return "";
  const { session_id: _session, remember: _remember, memory_generation: _generation, use_saved_preferences: _memoryRead, ...planning } = value;
  return JSON.stringify(canonical(planning));
}

export function samePlannerOrigin(left: Record<string, unknown> | null, right: Record<string, unknown>): boolean {
  if (!left) return false;
  const origin = (context: Record<string, unknown>) => {
    const location = context.location as { lat?: unknown; lon?: unknown } | undefined;
    return { lat: location?.lat, lon: location?.lon, language: context.language, starts_at: context.starts_at };
  };
  return JSON.stringify(origin(left)) === JSON.stringify(origin(right));
}

/** A control edit carries intent/exclusions without re-parsing an older message. */
export function conversationWithControls(previous: ConversationContext, context: Record<string, unknown>): ConversationContext {
  return { ...previous, duration_minutes: Number(context.duration_minutes), group_size: Number(context.group_size),
    indoor: Boolean(context.indoor), accessible: Boolean(context.accessible),
    airport_transfer_minutes: typeof context.airport_transfer_minutes === "number" ? context.airport_transfer_minutes : null };
}

/** Carry the planner's parsed explicit constraints into the visible controls. */
export function effectivePlannerContext(context: Record<string, unknown>, result: Recommendation): Record<string, unknown> {
  const conversation = result.conversation;
  const next = { ...context };
  if (Number.isInteger(result.context.memory_generation) && Number(result.context.memory_generation) >= 0) next.memory_generation = result.context.memory_generation;
  if (!conversation) return next;
  if (typeof conversation.duration_minutes === "number") next.duration_minutes = conversation.duration_minutes;
  if (typeof conversation.group_size === "number") next.group_size = conversation.group_size;
  if (typeof conversation.indoor === "boolean") next.indoor = conversation.indoor;
  if (typeof conversation.accessible === "boolean") next.accessible = conversation.accessible;
  if (conversation.airport_transfer_minutes !== undefined) next.airport_transfer_minutes = conversation.airport_transfer_minutes;
  return next;
}
