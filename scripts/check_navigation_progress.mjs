// Run with: node scripts/check_navigation_progress.mjs
// Uses the project's existing TypeScript dependency; no test framework is needed.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";

const source = await readFile(new URL("../src/lib/navigation-progress.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
});
const { advanceNavigationStep } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);

const latitude = 51.128, longitude = 71.43;
const metersPerDegree = 6_371_000 * Math.PI / 180;
const coordinate = (x, y) => [longitude + x / (metersPerDegree * Math.cos(latitude * Math.PI / 180)), latitude + y / metersPerDegree];
const position = (x, y, accuracy = 8) => {
  const [lon, lat] = coordinate(x, y);
  return { lon, lat, accuracy };
};
const geometry = [[0, 0], [100, 0], [100, 100], [200, 100], [200, 200], [300, 200]].map(([x, y]) => coordinate(x, y));
const steps = geometry.map((location, index) => ({
  location, geometry_start_index: index, geometry_end_index: Math.min(index + 1, geometry.length - 1),
}));

const probes = [
  ["GPS starts midway through the route", () => assert.equal(advanceNavigationStep(position(200, 150), geometry, steps, 0), 3)],
  ["GPS skips more than one turn between updates", () => assert.equal(advanceNavigationStep(position(250, 200), geometry, steps, 1), 4)],
  ["a fix before the next turn keeps the current instruction", () => assert.equal(advanceNavigationStep(position(100, 80), geometry, steps, 1), 1)],
  ["poor GPS accuracy does not advance", () => assert.equal(advanceNavigationStep(position(250, 200, 120), geometry, steps, 0), 0)],
  ["an off-route fix does not advance", () => assert.equal(advanceNavigationStep(position(250, 350), geometry, steps, 0), 0)],
  ["a backwards fix never reverses progress", () => assert.equal(advanceNavigationStep(position(50, 0), geometry, steps, 3), 3)],
  ["small backward GPS jitter never reverses progress", () => assert.equal(advanceNavigationStep(position(100, 95), geometry, steps, 2), 2)],
  ["maneuver locations work when provider indices are absent", () => assert.equal(advanceNavigationStep(position(200, 150), geometry, steps.map(({ location }) => ({ location })), 0), 3)],
  ["the final endpoint reaches the final instruction", () => assert.equal(advanceNavigationStep(position(300, 200), geometry, steps, 0), 5)],
  ["an invalid accuracy fix does not advance", () => assert.equal(advanceNavigationStep(position(250, 200, NaN), geometry, steps, 0), 0)],
  ["a crossing does not jump to a later pass through the same point", () => {
    const loop = [[0, 0], [100, 0], [100, 100], [0, 100], [0, 0], [-100, 0]].map(([x, y]) => coordinate(x, y));
    const loopSteps = loop.map((location, geometry_start_index) => ({ location, geometry_start_index }));
    assert.equal(advanceNavigationStep(position(0, 0), loop, loopSteps, 0), 0);
    assert.equal(advanceNavigationStep(position(0, 0), loop, loopSteps, 3), 4);
  }],
  ["global indices disambiguate duplicate arrival/departure positions", () => {
    const legSteps = [steps[0], steps[1], steps[1], ...steps.slice(2)];
    assert.equal(advanceNavigationStep(position(100, 40), geometry, legSteps, 0), 2);
  }],
];

for (const [name, probe] of probes) {
  probe();
  console.log(`PASS ${name}`);
}
console.log(`${probes.length} navigation-progress probes passed.`);
