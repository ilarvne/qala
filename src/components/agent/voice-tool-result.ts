import { effectivePlannerContext, planningContextKey } from "../../lib/planner-context";
import type { Recommendation } from "../../types";

export function voiceToolRecommendation(event: unknown, sessionContext: string, currentContext: string): { result: Recommendation; context: Record<string, unknown>; nextContext: string } | undefined {
  if (!event || typeof event !== "object") return;
  const wire = event as Record<string, unknown>;
  if (wire.tool_name !== "recommend_city_walk" || wire.is_error || wire.truncated || typeof wire.full_tool_result !== "string" || wire.full_tool_result.length > 2_000_000) return;
  try {
    const context = JSON.parse(sessionContext) as Record<string, unknown>;
    const current = JSON.parse(currentContext) as Record<string, unknown>;
    if (planningContextKey(context) !== planningContextKey(current)) return;
    const result = JSON.parse(wire.full_tool_result) as Recommendation;
    const location = context.location as { lat?: number; lon?: number } | undefined;
    const origin = result?.route?.coordinates?.[0];
    if (typeof result?.message !== "string" || !Array.isArray(result.recommendations) || result.recommendations.length > 3 ||
        !Number.isFinite(result.route?.total_minutes) || !result.context || !Array.isArray(origin) ||
        !Number.isFinite(location?.lat) || !Number.isFinite(location?.lon) ||
        !Number.isFinite(origin[0]) || !Number.isFinite(origin[1]) ||
        Math.abs(origin[0] - location!.lon!) > .0001 || Math.abs(origin[1] - location!.lat!) > .0001 ||
        result.recommendations.some((place) => typeof place.id !== "string" || !Number.isFinite(place.lat) || !Number.isFinite(place.lon))) return;
    return { result, context, nextContext: JSON.stringify(effectivePlannerContext(context, result)) };
  } catch { return; }
}
