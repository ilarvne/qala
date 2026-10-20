/** Run with `node scripts/check_assistant_adapter.mjs` after `npm ci`.
 * Exercises the bundled production adapter using isolated HTTP/SSE fixtures.
 */
import assert from "node:assert/strict";
import { build } from "esbuild";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = "src/components/agent/recommendation-adapter.ts";
const bundle = await build({ absWorkingDir: root, entryPoints: [source], bundle: true, platform: "node", format: "esm", write: false, logLevel: "silent" });
const { createRecommendationAdapter, branchConversation, samePlanningOrigin } = await import("data:text/javascript;base64," + Buffer.from(bundle.outputFiles[0].text).toString("base64"));
let checks = 0;
const check = {
  equal(...args) { assert.equal(...args); checks++; },
  deepEqual(...args) { assert.deepEqual(...args); checks++; },
  async rejects(...args) { await assert.rejects(...args); checks++; },
};
const originalFetch = globalThis.fetch;
const coverage = ["SSE chunk/CRLF boundaries", "real stage updates", "structured branch conversation", "planner context isolation", "canonical effective constraints", "UI filter edits retain coffee intent", "explicit version origin guard", "buffered deployment fallback", "cancel raceguard", "incomplete stream recovery", "sanitized server error"];
let failure;
try {
const context = { location: {lat:51.12,lon:71.43,label:'Bayterek'}, language:'en', starts_at:'2026-10-19T14:00:00+05:00', duration_minutes: 60, session_id: 'ephemeral-contract-test' };
const result = { message: 'A real result contract.', recommendations: [], route: {total_minutes: 0, walk_minutes: 0, distance_m: 0, coordinates: []}, context: {}, conversation: { duration_minutes: 30, interests:['coffee'], excluded_ids: ['poi:1'] }, mode: 'grounded', trace: [] };
const previousResult = {...result,conversation:{...result.conversation,duration_minutes:60}};
const previous = { role: 'assistant', content: [{type:'tool-call', toolName:'recommend_city_places', args:{requestContext:JSON.stringify(context)},result:previousResult}] };
check.deepEqual(branchConversation([previous],context),previousResult.conversation);
check.deepEqual(branchConversation([previous],{...context,duration_minutes:90}),{...previousResult.conversation,duration_minutes:90});
check.equal(branchConversation([],context),undefined);
const encoder = new TextEncoder();
function stream(parts) { return new ReadableStream({start(c){ for (const part of parts) c.enqueue(encoder.encode(part)); c.close(); }}); }
let sentBody; let applied = []; let calls = [];
const options = {language:'en',context,onResult:(r,c)=>applied.push([r,c])};
const adapter = createRecommendationAdapter(()=>options);
const messages = [previous,{id:'current-user',role:'user',content:[{type:'text',text:'Make it shorter'}]}];
globalThis.fetch = async (url, init) => { calls.push(url); sentBody=JSON.parse(init.body); return new Response(stream([': heartbeat\r\nevent: sta','tus\r\ndata: {"stage":"retrieve"}\r\n\r\nevent: status\ndata: {"stage":"validate"}\n\nevent: result\ndata: ',JSON.stringify(result).slice(0,43),JSON.stringify(result).slice(43)+'\n\n']),{headers:{'content-type':'text/event-stream'}}); };
const updates = [];
for await (const update of adapter.run({messages,abortSignal:new AbortController().signal})) updates.push(update);
check.deepEqual(calls,['/api/chat/stream']);
check.deepEqual(sentBody.conversation,previousResult.conversation);
check.deepEqual(updates.slice(0,2).map(u=>u.content[0].args.stage),['retrieve','validate']);
check.equal(updates.at(-1).status.type,'complete');
check.equal(updates.at(-1).content[1].result.message,result.message);
check.equal(applied.length,1);
check.deepEqual(applied[0][1],context);
const canonical = {...context,duration_minutes:30};
const completedTool = updates.at(-1).content[1];
check.deepEqual(JSON.parse(completedTool.args.requestContext),canonical);
const completedBranch = [...messages,{role:'assistant',content:updates.at(-1).content}];
check.deepEqual(branchConversation(completedBranch,canonical),result.conversation);
check.deepEqual(branchConversation(completedBranch,context),{...result.conversation,duration_minutes:60});
check.deepEqual(branchConversation(completedBranch,{...canonical,duration_minutes:45,group_size:4,indoor:true,accessible:true,airport_transfer_minutes:60}),{...result.conversation,duration_minutes:45,group_size:4,indoor:true,accessible:true,airport_transfer_minutes:60});
check.equal(branchConversation(completedBranch,{...canonical,location:{...canonical.location,lon:72}}),undefined);
check.equal(branchConversation(completedBranch,{...canonical,language:'ru'}),undefined);
check.equal(branchConversation(completedBranch,{...canonical,starts_at:'2026-10-20T14:00:00+05:00'}),undefined);
check.deepEqual(branchConversation(completedBranch,{...canonical,interests:['museum']}).interests,['museum']);
check.deepEqual(result.conversation.interests,['coffee']);
check.equal(samePlanningOrigin(context,{...context,duration_minutes:90,accessible:true,indoor:true,group_size:4}),true);
check.equal(samePlanningOrigin(context,{...context,location:{...context.location,lat:52}}),false);
check.equal(samePlanningOrigin(context,{...context,language:'ru'}),false);
check.equal(samePlanningOrigin(context,{...context,starts_at:'2026-10-20T14:00:00+05:00'}),false);
check.equal(samePlanningOrigin(context,{...context,location:{...context.location,label:'Same location'}}),true);

applied=[]; calls=[];
globalThis.fetch = async (url) => { calls.push(url); return url==='/api/chat/stream' ? new Response('',{status:404}) : Response.json(result); };
for await (const _ of adapter.run({messages,abortSignal:new AbortController().signal})) {}
check.deepEqual(calls,['/api/chat/stream','/api/chat']);
check.equal(applied.length,1);

applied=[]; const aborted = new AbortController();
globalThis.fetch = async () => { aborted.abort(); return Response.json(result); };
await check.rejects(async()=>{for await (const _ of adapter.run({messages,abortSignal:aborted.signal})){};}, {name:'AbortError'});
check.equal(applied.length,0);

applied=[];
globalThis.fetch = async () => new Response(stream(['event: status\ndata: {"stage":"compose"}\n\n']),{headers:{'content-type':'text/event-stream'}});
await check.rejects(async()=>{for await (const _ of adapter.run({messages,abortSignal:new AbortController().signal})){};},/unavailable/);
check.equal(applied.length,0);

globalThis.fetch = async () => new Response(stream(['event: error\ndata: {"message":"Please try again later."}\n\n']),{headers:{'content-type':'text/event-stream'}});
await check.rejects(async()=>{for await (const _ of adapter.run({messages,abortSignal:new AbortController().signal})){};},/Please try again later/);

} catch (error) {
  failure = error;
} finally {
  globalThis.fetch = originalFetch;
}
const sourceHashes = Object.fromEntries(await Promise.all([source, "src/lib/planner-context.ts", "src/lib/api.ts"].map(async (path) => [path, createHash("sha256").update(await readFile(resolve(root, path))).digest("hex")])));
const report = { checked_at: new Date().toISOString(), command: "node scripts/check_assistant_adapter.mjs", passed: !failure, assertions_passed: checks, coverage, scope: "Isolated contract tests of the bundled production adapter using protocol fixtures; no live provider or browser claims.", source_sha256: sourceHashes, ...(failure ? { error: String(failure.message || failure) } : {}) };
await mkdir(resolve(root, "artifacts"), { recursive: true });
await writeFile(resolve(root, "artifacts/assistant-adapter-verification.json"), JSON.stringify(report, null, 2) + "\n");
console.log(JSON.stringify(report, null, 2));
if (failure) throw failure;
