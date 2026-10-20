import type { Recommendation } from "../../types";
import { samePlanningOrigin } from "./recommendation-adapter";

interface ResultSelection {
  result: Recommendation;
  placeId: string;
  requestContext: unknown;
  currentContext: Record<string, unknown>;
  message?: unknown;
  cancelRunning: () => void;
  onQuery?: (message: string) => void;
  restore: (result: Recommendation, currentContext: Record<string, unknown>) => void;
  select: (id: string, restoring: Recommendation) => void;
}

/** A historical map action first restores its own guarded plan, then selects.
 * The plan identity accompanies selection so the App can preserve that choice
 * when its result-change effect commits instead of resetting to the first stop.
 */
export function restoreResultSelection(options: ResultSelection): boolean {
  if (!options.result.recommendations.some((place) => place.id === options.placeId)) return false;
  let captured: unknown;
  try {
    captured = typeof options.requestContext === "string" ? JSON.parse(options.requestContext) : options.requestContext;
  } catch { return false; }
  if (!captured || typeof captured !== "object" || Array.isArray(captured) ||
      !samePlanningOrigin(captured as Record<string, unknown>, options.currentContext)) return false;
  options.cancelRunning();
  if (typeof options.message === "string") options.onQuery?.(options.message);
  options.restore(options.result, options.currentContext);
  options.select(options.placeId, options.result);
  return true;
}
