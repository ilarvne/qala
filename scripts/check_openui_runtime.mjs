/** Run with `node scripts/check_openui_runtime.mjs` after `npm ci`.
 * Uses the real Python serializer, installed OpenUI parser/React runtime and SSR.
 * Captured component event handlers exercise real runtime actions/form state.
 */
import assert from "node:assert/strict";
import { build } from "esbuild";
import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createParser } from "@openuidev/react-lang";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const cache = resolve(root, "node_modules/.cache");
await mkdir(cache, { recursive: true });
const temp = await mkdtemp(join(cache, "qala-openui-check-"));
let checks = 0;
const check = {
  equal(...args) { assert.equal(...args); checks++; },
  deepEqual(...args) { assert.deepEqual(...args); checks++; },
  ok(...args) { assert.ok(...args); checks++; },
};
let failure;
try {
  const output = join(temp, "openui.mjs");
  await build({ absWorkingDir: root, entryPoints: ["src/components/OpenUIResponse.tsx"], bundle: true, platform: "node", format: "esm", packages: "external", jsx: "automatic", loader: { ".css": "empty" }, outfile: output, logLevel: "silent" });
  const { OpenUIResponse, cityResponseLibrary } = await import(pathToFileURL(output).href);
  const parser = createParser(cityResponseLibrary.toJSONSchema(), cityResponseLibrary.root);
  const python = existsSync(resolve(root, ".venv/bin/python")) ? resolve(root, ".venv/bin/python") : "python3";
  function program(result, message = "") {
    const process = spawnSync(python, ["-c", "import json,sys;from backend.openui import build_openui;print(json.dumps(build_openui(json.loads(sys.argv[1]),sys.argv[2])))", JSON.stringify(result), message], { cwd: root, encoding: "utf8" });
    if (process.status !== 0) throw new Error(process.stderr);
    const wire = JSON.parse(process.stdout);
    const parsed = parser.parse(wire.document);
    check.deepEqual(parsed.meta.errors, []);
    check.deepEqual(parsed.meta.unresolved, []);
    check.equal(parsed.root.typeName, "CityResponse");
    return { wire, parsed };
  }
  const place = (id, name) => ({ id, name, lat: 51.12, lon: 71.43, category: "culture", description: "Sourced test fixture.", why: "Near the starting point.", action: "Walk through public space.", visit_minutes: 15, walk_minutes: 5, distance_m: 500, leg_distance_m: 500, hours_status: "unknown", hours: null, confidence: "source", source: { name: "OpenStreetMap", url: "https://www.openstreetmap.org/node/123" }, photos: [{ url: "/photos/fixture.jpg", source_url: "https://commons.wikimedia.org/wiki/File:Example.jpg", author: "Test fixture", license: "CC BY-SA 4.0", license_url: "https://creativecommons.org/licenses/by-sa/4.0/" }], tags: [] });
  const result = { message: "A walk.", recommendations: [place("osm:node/123", "Bayterek"), place('quote\" and Кириллица', "Second place")], route: { total_minutes: 45, walk_minutes: 10, distance_m: 900, coordinates: [], estimated: true }, context: { duration_minutes: 60 }, conversation: { duration_minutes: 60, group_size: 1, indoor: false, accessible: false, interests: ["coffee"] }, followups: ["Less walking"] };
  const itinerary = program(result);
  check.equal(itinerary.wire.layout, "itinerary");
  const places = itinerary.parsed.root.props.children.find((node) => node.typeName === "Itinerary").props.places;
  check.deepEqual(places.map((node) => node.props.id), result.recommendations.map((item) => item.id));
  const compare = program(result, "compare these places");
  check.equal(compare.wire.layout, "comparison");
  check.deepEqual(compare.parsed.root.props.children.find((node) => node.typeName === "Comparison").props.ids, result.recommendations.map((item) => item.id));
  const empty = { ...result, recommendations: [], followups: [], clarifications: [{ field: "airport_transfer_minutes", message: "How much time for transfer?", options: [{ label: "60 minutes", value: 60 }] }] };
  const clarify = program(empty);
  check.equal(clarify.wire.layout, "clarification");
  check.ok(clarify.parsed.root.props.children.some((node) => node.typeName === "Clarifications"));
  const capped = program({ ...result, recommendations: [1,2,3,4].map((id) => place(String(id), String(id))) });
  check.equal(capped.parsed.root.props.children.find((node) => node.typeName === "Itinerary").props.places.length, 3);
  check.ok(parser.parse("root = ArbitraryWidget()").meta.errors.some((error) => error.code === "unknown-component"));

  const captured = {};
  for (const name of ["PlanControls", "PlaceOption", "FollowUps", "Clarifications"]) {
    const definition = cityResponseLibrary.components[name];
    const original = definition.component;
    definition.component = (props) => {
      const element = original(props);
      (captured[name] ??= []).push({ props, element });
      return element;
    };
  }
  const actions = { select: [], inspect: [], save: [], followup: [], refine: [] };
  function render(payload, wire) {
    for (const name of Object.keys(captured)) captured[name] = [];
    return renderToStaticMarkup(React.createElement(OpenUIResponse, { result: { ...payload, openui: wire }, language: "en", savedIds: [], onSelect: (id) => actions.select.push(id), onInspect: (value) => actions.inspect.push(value.id), onSave: (value) => actions.save.push(value.id), onFollowUp: (value) => actions.followup.push(value), onRefine: (value) => actions.refine.push(value) }));
  }
  const html = render(result, itinerary.wire);
  check.ok(html.includes("Bayterek"));
  check.ok(html.includes("Update plan"));
  check.ok(html.includes("Less walking"));
  check.ok(html.includes('class="qa-plan-duration">45 min'));
  const mistakenPhoto = { ...result, recommendations: [{ ...result.recommendations[0], name: "Ботаника кофе", photos: [] }] };
  check.equal(render(mistakenPhoto, program(mistakenPhoto).wire).includes("botanical.jpg"), false);
  check.equal(render(mistakenPhoto, program(mistakenPhoto).wire).includes("oui-place-photo"), false);
  const weatherResult = { ...result, context: { weather: { status: "available", temperature_c: -4, apparent_temperature_c: -9, wind_kmh: 17, precipitation_mm: 0, valid_at: "2026-10-20T14:00:00+05:00", source_url: "https://open-meteo.com/", attribution: "Weather data by Open-Meteo (CC BY 4.0)" }, weather_effect: { applied: true } } };
  const weatherHtml = render(weatherResult, itinerary.wire);
  check.ok(weatherHtml.includes("-4°C") && weatherHtml.includes("-9°C") && weatherHtml.includes("17 km/h"));
  check.ok(weatherHtml.includes("CC BY 4.0") && weatherHtml.includes("Weather considered"));
  check.equal(render({ ...weatherResult, context: { weather: { ...weatherResult.context.weather, temperature_c: NaN, source_url: "javascript:alert(1)" } } }, itinerary.wire).includes("javascript:"), false);
  const calendar = { ...result, recommendations: [], events: [{ id: "official-event", title: "A concert <script>bad()</script>", url: "https://astanavenue.kz/events/test", date: "2026-10-28", start_time: null, date_precision: "day", venue: null, poi_id: null, availability: "unverified" }] };
  const calendarHtml = render(calendar, program(calendar).wire);
  check.ok(calendarHtml.includes("official-events") && calendarHtml.includes("Time, venue and tickets"));
  check.ok(calendarHtml.includes("&lt;script&gt;") && !calendarHtml.includes("<script>"));
  check.equal(render({ ...calendar, context: weatherResult.context }, program(calendar).wire).includes("Estimated walking until"), false);
  check.equal(render({ ...calendar, events: [{ ...calendar.events[0], url: "javascript:alert(1)" }] }, program(calendar).wire).includes("official-events"), false);
  // Restore handler captures before exercising the original itinerary actions.
  render(result, itinerary.wire);
  const first = captured.PlaceOption[0].element;
  first.props.children[0].props.children[1].props.onClick();
  first.props.children[0].props.children[2].props.onClick();
  first.props.children[1].props.onClick();
  check.deepEqual(actions.select, [result.recommendations[0].id]);
  check.deepEqual(actions.save, [result.recommendations[0].id]);
  check.deepEqual(actions.inspect, [result.recommendations[0].id]);
  const followup = captured.FollowUps[0].element.props.children[0];
  followup.props.onClick();
  check.deepEqual(actions.followup, ["Less walking"]);

  const controls = captured.PlanControls.at(-1).element.props.children[1];
  const row = controls.props.children[0];
  const durationSelect = row.props.children[0].props.children[1];
  const groupSelect = row.props.children[1].props.children[1];
  durationSelect.props.onValueChange("45");
  groupSelect.props.onValueChange("4");
  controls.props.children[1].props.children[0].props.onChange({ target: { checked: false } });
  controls.props.children[2].props.children[0].props.onChange({ target: { checked: false } });
  controls.props.onSubmit({ preventDefault() {} });
  check.deepEqual(actions.refine.at(-1), { duration: 45, group: 4, indoor: false, accessible: false });
  durationSelect.props.onValueChange("NaN");
  controls.props.onSubmit({ preventDefault() {} });
  check.equal(actions.refine.length, 1);
  durationSelect.props.onValueChange("5000");
  groupSelect.props.onValueChange("50");
  controls.props.onSubmit({ preventDefault() {} });
  check.deepEqual(actions.refine.at(-1), { duration: 480, group: 20, indoor: false, accessible: false });

  const foreign = { ...itinerary.wire, document: itinerary.wire.document.replace('@SelectPlace("osm:node/123")', '@SelectPlace("not-in-result")').replace('@SavePlace("osm:node/123")', '@SavePlace("not-in-result")').replace('@InspectPlace("osm:node/123")', '@InspectPlace("not-in-result")') };
  render(result, foreign);
  const foreignPlace = captured.PlaceOption[0].element;
  foreignPlace.props.children[0].props.children[1].props.onClick();
  foreignPlace.props.children[0].props.children[2].props.onClick();
  foreignPlace.props.children[1].props.onClick();
  check.equal(actions.select.length, 1);
  check.equal(actions.save.length, 1);
  check.equal(actions.inspect.length, 1);
  const unknown = { ...itinerary.wire, document: 'root = CityResponse([places])\nplaces = Itinerary([PlaceOption("not-in-result", @SelectPlace("not-in-result"), @InspectPlace("not-in-result"), @SavePlace("not-in-result"))])' };
  check.equal(render(result, unknown).includes('data-openui-place="not-in-result"'), false);
  check.equal(render(result, { ...itinerary.wire, document: "root = Query(\"anything\")" }), "");
  check.equal(render(result, { ...itinerary.wire, version: 999 }), "");
  render(empty, clarify.wire);
  captured.Clarifications[0].element.props.children[0].props.children[1].props.children[0].props.onClick();
  check.deepEqual(actions.refine.at(-1), { airportTransfer: 60 });
  const followupCount = actions.followup.length;
  for (const field of ["indoor", "accessible"]) {
    render({ ...empty, clarifications: [{ field, message: "No matching place.", options: [{ label: `Remove the ${field} filter`, value: false }] }] }, clarify.wire);
    captured.Clarifications[0].element.props.children[0].props.children[1].props.children[0].props.onClick();
    check.deepEqual(actions.refine.at(-1), { [field]: false });
  }
  check.equal(actions.followup.length, followupCount);
} catch (error) {
  failure = error;
} finally {
  await rm(temp, { recursive: true, force: true });
}
const paths = ["src/components/OpenUIResponse.tsx", "src/components/ContextSources.tsx", "backend/openui.py", "src/lib/place-data.ts"];
const sourceHashes = Object.fromEntries(await Promise.all(paths.map(async (path) => [path, createHash("sha256").update(await readFile(resolve(root, path))).digest("hex")])));
const report = { checked_at: new Date().toISOString(), command: "node scripts/check_openui_runtime.mjs", passed: !failure, assertions_passed: checks, coverage: ["Real Python OpenUI programs and installed parser", "Itinerary/comparison/clarification and bounded places", "Quoted/non-Latin ID escaping", "SSR trusted facts and route totals", "Native runtime select/inspect/save/followup actions", "Wrapped form values, false booleans and finite numeric guards", "Unknown place action guards", "Blocked query/version inputs", "Airport transfer clarification", "Boolean clarification removes filters through typed context without reparsing the label"], scope: "Production serializer/parser/runtime contract tests using explicit POI fixtures; no live POI or browser visual claims.", source_sha256: sourceHashes, ...(failure ? { error: String(failure.message || failure) } : {}) };
await mkdir(resolve(root, "artifacts"), { recursive: true });
await writeFile(resolve(root, "artifacts/openui-runtime-verification.json"), JSON.stringify(report, null, 2) + "\n");
console.log(JSON.stringify(report, null, 2));
if (failure) throw failure;
