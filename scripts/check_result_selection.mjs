/** Production-controller regression for historical assistant map actions.
 * Run: node scripts/check_result_selection.mjs
 * App pending-selection commit wiring remains separately typechecked/reviewed.
 */
import assert from "node:assert/strict";
import { build } from "esbuild";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = "src/components/agent/result-selection.ts";
const bundle = await build({ absWorkingDir: root, entryPoints: [source], bundle: true, platform: "node", format: "esm", write: false, logLevel: "silent" });
const { restoreResultSelection } = await import("data:text/javascript;base64," + Buffer.from(bundle.outputFiles[0].text).toString("base64"));
let assertions = 0;
const check = { equal(...args) { assert.equal(...args); assertions++; }, deepEqual(...args) { assert.deepEqual(...args); assertions++; } };
let failure;
try {
  const captured = { location: { lat: 51.12, lon: 71.43 }, language: "en", starts_at: "2026-10-19T14:00:00+05:00", duration_minutes: 60, remember: true, memory_generation: 1 };
  const current = { ...captured, duration_minutes: 30, remember: false, memory_generation: 2 };
  const sourcePlan = { message: "Original plan fixture.", recommendations: [{ id: "old-first" }, { id: "old-selected" }], route: { total_minutes: 60, coordinates: [[71.43,51.12],[71.44,51.13]] }, context: {}, conversation: { duration_minutes: 60, interests: ["coffee"] } };
  const currentPlan = { ...sourcePlan, recommendations: [{ id: "new-alternative" }] };
  check.equal(currentPlan.recommendations.some((place) => place.id === "old-selected"), false);
  const events = [];
  let restored, restoredContext, selected, restoring;
  const options = {
    result: sourcePlan, placeId: "old-selected", requestContext: JSON.stringify(captured), currentContext: current, message: "Original coffee request",
    cancelRunning() { events.push("cancel"); },
    onQuery(message) { events.push("query:" + message); },
    restore(plan, context) { events.push("restore"); restored = plan; restoredContext = context; },
    select(id, plan) { events.push("select"); selected = id; restoring = plan; },
  };
  check.equal(restoreResultSelection(options), true);
  check.deepEqual(events, ["cancel", "query:Original coffee request", "restore", "select"]);
  check.equal(restored, sourcePlan);
  check.equal(restoredContext, current);
  check.equal(restoredContext.remember, false);
  check.equal(restoredContext.memory_generation, 2);
  check.equal(selected, "old-selected");
  check.equal(restoring, sourcePlan);
  check.equal(restoring.recommendations[1].id, selected);
  check.deepEqual(restoring.conversation.interests, ["coffee"]);
  const eventCount = events.length;
  const denied = [
    { placeId: "not-in-source" },
    { currentContext: { ...current, location: { ...current.location, lat: 52 } } },
    { currentContext: { ...current, language: "ru" } },
    { currentContext: { ...current, starts_at: "2026-10-20T14:00:00+05:00" } },
    { requestContext: "{malformed" },
    { requestContext: undefined },
    { requestContext: [] },
  ];
  for (const variation of denied) {
    check.equal(restoreResultSelection({ ...options, ...variation }), false);
    check.equal(events.length, eventCount);
  }
  const noQueryEvents = [];
  check.equal(restoreResultSelection({ ...options, message: undefined, cancelRunning: () => noQueryEvents.push("cancel"), restore: () => noQueryEvents.push("restore"), select: () => noQueryEvents.push("select") }), true);
  check.deepEqual(noQueryEvents, ["cancel", "restore", "select"]);
  // An already-current plan still emits an explicit selection, letting the App
  // handle it immediately instead of leaving a pending ID for a future result.
  check.equal(restoreResultSelection({ ...options, result: currentPlan, placeId: "new-alternative" }), true);
  check.equal(restoring, currentPlan);
  check.equal(selected, "new-alternative");
} catch (error) {
  failure = error;
}
const sourceHash = createHash("sha256").update(await readFile(resolve(root, source))).digest("hex");
const report = { checked_at: new Date().toISOString(), command: "node scripts/check_result_selection.mjs", passed: !failure, assertions_passed: assertions, coverage: ["Historical POI absent from the current alternatives", "Restore source plan before selecting a non-first stop", "Cancel active generation before explicit restoration", "Retain latest consent and memory generation in acceptance context", "Reject unknown IDs and cross-location/language/time restoration", "Reject malformed or missing source context", "Already-current plan identity remains explicit"], scope: "Bundled production controller with explicit plan fixtures. App commit-selection wiring is separately reviewed/typechecked; no browser rerun claim.", source_sha256: { [source]: sourceHash }, ...(failure ? { error: String(failure.message || failure) } : {}) };
await mkdir(resolve(root, "artifacts"), { recursive: true });
await writeFile(resolve(root, "artifacts/assistant-result-selection-verification.json"), JSON.stringify(report, null, 2) + "\n");
console.log(JSON.stringify(report, null, 2));
if (failure) throw failure;
