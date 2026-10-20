#!/usr/bin/env python3
"""Exercise the real React planner hook with controlled HTTP delivery.

Uses browser React/StrictMode, not a reimplementation of the hook. Transport
fixtures isolate consent ordering and planning state; they are not POI/RAG proof.
Run: /usr/bin/python3 scripts/verify_planner_hooks.py
"""
from __future__ import annotations

import functools
import hashlib
import http.server
import json
import subprocess
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
checks = []
HARNESS = r'''
import React from "react";
import {createRoot} from "react-dom/client";
import {usePlanner} from "./src/hooks/usePlanner";
window.__transport = {requests: [], errors: []};
window.fetch = (input, init = {}) => new Promise((resolve, reject) => {
  const entry = {id: window.__transport.requests.length, path: String(input), method: init.method || "GET", body: init.body ? JSON.parse(init.body) : null, pending: true, aborted: false};
  entry.respond = (data, status = 200) => {entry.pending = false; resolve(new Response(JSON.stringify(data), {status, headers: {"Content-Type": "application/json"}}));};
  entry.fail = () => {entry.pending = false; reject(new TypeError("Controlled transport failure"));};
  if (init.signal) init.signal.addEventListener("abort", () => {entry.aborted = true; entry.pending = false; reject(new DOMException("Aborted", "AbortError"));}, {once:true});
  window.__transport.requests.push(entry);
});
function Probe() {
  const planner = usePlanner();
  window.__planner = planner;
  window.__state = {settings: planner.settings, remember: planner.remember, memoryBusy: planner.memoryBusy, memoryPreferences: planner.memoryPreferences, context: planner.context, result: planner.result, current: planner.current, loading: planner.loading};
  return React.createElement("output", {id:"state"}, JSON.stringify(window.__state));
}
createRoot(document.getElementById("root")).render(React.createElement(React.StrictMode, null, React.createElement(Probe)));
window.__invoke = (method, ...args) => {const value = window.__planner[method](...args); if (value?.catch) value.catch(error => window.__transport.errors.push(error.message));};
'''


def check(name, condition, detail=None):
    checks.append({"check": name, "passed": bool(condition), **({"detail": detail} if detail is not None else {})})
    print(("PASS " if condition else "FAIL ") + name, flush=True)
    if not condition:
        raise AssertionError(name)


def requests(page, method=None, suffix=None, pending=False):
    return page.evaluate("({method,suffix,pending}) => window.__transport.requests.filter(r => !r.aborted && (!method || r.method === method) && (!suffix || r.path.includes(suffix)) && (!pending || r.pending)).map(({id,path,method,body,pending}) => ({id,path,method,body,pending}))", {"method": method, "suffix": suffix, "pending": pending})


def await_request(page, method, suffix):
    page.wait_for_function("({method,suffix}) => window.__transport.requests.some(r => !r.aborted && r.pending && r.method === method && r.path.includes(suffix))", arg={"method": method, "suffix": suffix})
    return requests(page, method, suffix, True)[-1]


def respond(page, request, data, status=200):
    page.evaluate("({id,data,status}) => window.__transport.requests[id].respond(data,status)", {"id": request["id"], "data": data, "status": status})


def state(page):
    return page.evaluate("window.__state")


def call(page, method, *args):
    page.evaluate("({method,args}) => window.__invoke(method,...args)", {"method": method, "args": list(args)})


def result_for(body, name="plan", **changes):
    conversation = {"interests": body.get("interests", []), "excluded_ids": [], "last_recommendation_ids": [], "excluded_categories": [], "duration_minutes": body.get("duration_minutes", 60), "group_size": body.get("group_size", 1), "indoor": body.get("indoor", False), "accessible": body.get("accessible", False), "airport": False, "airport_transfer_minutes": body.get("airport_transfer_minutes"), "max_walk_minutes": None, **changes}
    return {"message": name, "recommendations": [], "route": {"total_minutes": 0, "walk_minutes": 0, "distance_m": 0, "coordinates": []}, "context": {"memory_generation": body.get("memory_generation", 0)}, "conversation": conversation, "trace": [], "mode": "controlled-hook-fixture"}


def bootstrap(page, preferences=None, generation=0):
    request = await_request(page, "GET", "/api/memory/")
    respond(page, request, {"preferences": preferences, "generation": generation})
    plan = await_request(page, "POST", "/api/recommend")
    respond(page, plan, result_for(plan["body"], interests=(preferences or {}).get("interests", [])))
    page.wait_for_function("window.__state.result && !window.__state.loading")
    return plan


def new_page(browser, base, storage=None):
    context = browser.new_context()
    if storage:
        context.add_init_script("for (const [key,value] of Object.entries(" + json.dumps(storage) + ")) localStorage.setItem(key,value)")
    page = context.new_page()
    page.goto(base, wait_until="domcontentloaded")
    page.wait_for_function("window.__planner")
    return context, page


def controls_and_consent(browser, base):
    context, page = new_page(browser, base)
    try:
        bootstrap(page)
        check("anonymous visit does not persist a memory capability", page.evaluate("localStorage.getItem('qala-memory-session') === null"))
        check("anonymous planning does not read persistent preferences", state(page)["context"]["use_saved_preferences"] is False)
        captured = state(page)["context"]
        initial = result_for(captured, "30-minute conversation", duration_minutes=30, group_size=3, indoor=True, interests=["coffee"], excluded_categories=["museum"])
        call(page, "acceptResult", initial, captured)
        call(page, "setLastQuery", "Indoor coffee for 30 minutes for a group of 3")
        call(page, "update", {"duration": 90, "indoor": False, "group": 1})
        req = await_request(page, "POST", "/api/recommend")
        body = req["body"]
        check("explicit controls do not resend an older natural-language budget", "30 minutes" not in body["message"] and body["duration_minutes"] == 90)
        check("structured control refresh preserves intent and exclusion while overriding time/group/indoor", body["conversation"]["interests"] == ["coffee"] and body["conversation"]["excluded_categories"] == ["museum"] and body["conversation"]["duration_minutes"] == 90 and body["conversation"]["group_size"] == 1 and body["conversation"]["indoor"] is False)
        respond(page, req, result_for(body, "90-minute plan", **body["conversation"]))
        page.wait_for_function("window.__state.result.message === '90-minute plan'")
        check("new explicit controls remain current after the reply", state(page)["current"] and state(page)["settings"]["duration"] == 90)
        before = len(requests(page, "POST", "/api/recommend"))
        call(page, "changeRemember", True)
        save = await_request(page, "POST", "/api/memory/")
        check("memory enable uses current consent generation and curated interests", save["body"]["memory_generation"] == 0 and save["body"]["interests"] == ["coffee"] and "location" not in save["body"])
        respond(page, save, {"generation": 1, "preferences": {"interests": ["coffee"], "duration_minutes": 90}})
        page.wait_for_function("window.__state.remember && !window.__state.memoryBusy")
        check("memory save does not replan", len(requests(page, "POST", "/api/recommend")) == before)
        check("only an opted-in capability is persisted", page.evaluate("Object.keys(localStorage).length === 1 && localStorage.getItem('qala-memory-session') === window.__state.context.session_id"))
        old_context = state(page)["context"]
        call(page, "changeRemember", False)
        deletion = await_request(page, "DELETE", "/api/memory/")
        check("forget revokes outgoing consent before DELETE delivery", not state(page)["remember"] and not state(page)["context"]["remember"] and page.evaluate("localStorage.getItem('qala-memory-session') === null"))
        check("revocation also disables reading stored preferences", state(page)["context"]["use_saved_preferences"] is False)
        reads = len(requests(page, "GET", "/api/memory/"))
        call(page, "inspectMemory")
        check("inspection cannot invalidate an in-flight memory mutation", len(requests(page, "GET", "/api/memory/")) == reads)
        call(page, "acceptResult", result_for(old_context, "chat completed across consent change", duration_minutes=90), old_context)
        check("consent-only changes do not discard an otherwise current chat result", state(page)["result"]["message"] == "chat completed across consent change" and not state(page)["remember"])
        respond(page, deletion, {"generation": 2, "preferences": None})
        page.wait_for_function("!window.__state.memoryBusy")
        check("completed deletion preserves the current plan", state(page)["current"] and state(page)["context"]["memory_generation"] == 2 and not state(page)["remember"])
        call(page, "update", {"language": "ru"})
        changed = await_request(page, "POST", "/api/recommend")
        check("language/origin context changes intentionally reset inherited turn constraints", "conversation" not in changed["body"])
    finally:
        context.close()


def saved_bootstrap_and_failure(browser, base):
    cap = "persistent-memory-capability-1234567890"
    context, page = new_page(browser, base, {"qala-memory-session": cap})
    preferences = {"interests": ["coffee"], "language": "ru", "duration_minutes": 45, "indoor": True, "accessible": True}
    try:
        plan = bootstrap(page, preferences, 4)
        check("saved capability is restored without the previous tab's sessionStorage", cap in requests(page, "GET", "/api/memory/")[-1]["path"])
        body = plan["body"]
        check("initial read restores remembered language/time/accessibility before planning", body["language"] == "ru" and body["duration_minutes"] == 45 and body["indoor"] and body["accessible"] and body["interests"] == ["coffee"] and body["memory_generation"] == 4)
        check("remembered bootstrap reads opted-in preferences without writing a new profile", body["use_saved_preferences"] is True and body["remember"] is False)
        read = None
        call(page, "inspectMemory")
        read = await_request(page, "GET", "/api/memory/")
        call(page, "changeRemember", False)
        delete = await_request(page, "DELETE", "/api/memory/")
        respond(page, read, {"generation": 4, "preferences": preferences})
        respond(page, delete, {"detail": "Controlled deletion failure"}, 500)
        page.wait_for_function("!window.__state.memoryBusy")
        check("an older inspector read and failed DELETE cannot re-enable consent", not state(page)["remember"] and page.evaluate("localStorage.getItem('qala-memory-session') === null"))
        page.reload(wait_until="domcontentloaded")
        revoked_boot = bootstrap(page, preferences, 4)
        check("failed revocation remains locally off after reload", not state(page)["remember"] and not state(page)["context"]["remember"])
        check("failed revocation does not hydrate or use the undeleted server profile", revoked_boot["body"]["use_saved_preferences"] is False and revoked_boot["body"]["duration_minutes"] == 60 and revoked_boot["body"]["language"] == "en")
    finally:
        context.close()


def write_order_and_stale_generation(browser, base):
    context, page = new_page(browser, base)
    try:
        bootstrap(page)
        call(page, "changeRemember", True)
        save = await_request(page, "POST", "/api/memory/")
        call(page, "changeRemember", False)
        check("memory mutations serialize behind a pending save", not requests(page, "DELETE", "/api/memory/"))
        respond(page, save, {"generation": 1, "preferences": {"interests": ["coffee"]}})
        delete = await_request(page, "DELETE", "/api/memory/")
        check("older save completion cannot restore consent or release busy while deletion remains pending", not state(page)["remember"] and state(page)["memoryBusy"] and page.evaluate("localStorage.getItem('qala-memory-session') === null"))
        respond(page, delete, {"generation": 2, "preferences": None})
        page.wait_for_function("!window.__state.memoryBusy")
        call(page, "changeRemember", True)
        stale = await_request(page, "POST", "/api/memory/")
        respond(page, stale, {"detail": "Consent generation changed"}, 409)
        refresh = await_request(page, "GET", "/api/memory/")
        respond(page, refresh, {"generation": 3, "preferences": None})
        page.wait_for_function("!window.__state.memoryBusy")
        check("a stale memory write refreshes the epoch without automatic retry or opt-in", len(requests(page, "POST", "/api/memory/")) == 2 and not state(page)["remember"] and state(page)["context"]["memory_generation"] == 3)
        call(page, "changeRemember", True)
        fresh = await_request(page, "POST", "/api/memory/")
        check("a new explicit consent uses the refreshed generation", fresh["body"]["memory_generation"] == 3)
        respond(page, fresh, {"generation": 4, "preferences": {"interests": ["nature"]}})
        page.wait_for_function("window.__state.remember && !window.__state.memoryBusy")
        captured = state(page)["context"]
        delayed = result_for(captured, "old revoked chat")
        delayed["context"] = {"memory_generation": 3, "memory_revoked_during_request": True}
        call(page, "acceptResult", delayed, captured)
        check("an old revoked reply cannot undo a newer explicit opt-in", state(page)["remember"] and state(page)["context"]["memory_generation"] == 4)
        second = context.new_page()
        second.goto(base, wait_until="domcontentloaded")
        restored = await_request(second, "GET", "/api/memory/")
        check("a new tab restores the explicitly persisted capability", state(page)["context"]["session_id"] in restored["path"])
        second.evaluate("localStorage.removeItem('qala-memory-session')")
        page.wait_for_function("!window.__state.remember")
        check("forgetting in another tab revokes outgoing consent here", not state(page)["context"]["remember"])
    finally:
        context.close()


def startup_and_inspector_order(browser, base):
    context, page = new_page(browser, base)
    try:
        old_boot = await_request(page, "GET", "/api/memory/")
        call(page, "update", {"duration": 90})
        updated = await_request(page, "POST", "/api/recommend")
        respond(page, updated, result_for(updated["body"], "explicit 90"))
        page.wait_for_function("window.__state.result?.message === 'explicit 90'")
        respond(page, old_boot, {"generation": 1, "preferences": {"interests": ["coffee"], "duration_minutes": 45}})
        page.wait_for_function("window.__state.context.memory_generation === 1")
        check("late bootstrap cannot overwrite user controls or launch a default plan", state(page)["settings"]["duration"] == 90 and len(requests(page, "POST", "/api/recommend")) == 1)
        call(page, "inspectMemory")
        old_read = await_request(page, "GET", "/api/memory/")
        call(page, "editMemory", ["nature"])
        save = await_request(page, "POST", "/api/memory/")
        respond(page, save, {"generation": 2, "preferences": {"interests": ["nature"]}})
        page.wait_for_function("!window.__state.memoryBusy")
        respond(page, old_read, {"generation": 1, "preferences": {"interests": ["coffee"]}})
        page.wait_for_timeout(30)
        check("older inspector responses cannot restore edited interests", state(page)["memoryPreferences"]["interests"] == ["nature"])
    finally:
        context.close()


def main():
    with tempfile.TemporaryDirectory(prefix="qala-hook-contract-") as directory:
        directory = Path(directory)
        build = {"stdin": {"contents": HARNESS, "resolveDir": str(ROOT), "loader": "tsx"}, "bundle": True, "format": "esm", "platform": "browser", "outfile": str(directory / "probe.js"), "alias": {"@": str(ROOT / "src")}, "define": {"process.env.NODE_ENV": '"development"'}}
        subprocess.run(["node", "--input-type=module", "-e", "import {build} from 'esbuild';await build(" + json.dumps(build) + ")"], cwd=ROOT, check=True)
        (directory / "index.html").write_text('<!doctype html><html><body><main id="root"></main><script type="module" src="/probe.js"></script></body></html>')
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *_):
                pass
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(directory)))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True, executable_path="/usr/bin/chromium", args=["--no-sandbox"])
                try:
                    base = "http://127.0.0.1:" + str(server.server_port)
                    controls_and_consent(browser, base)
                    saved_bootstrap_and_failure(browser, base)
                    write_order_and_stale_generation(browser, base)
                    startup_and_inspector_order(browser, base)
                finally:
                    browser.close()
        finally:
            server.shutdown(); server.server_close()
    report = {"passed": all(c["passed"] for c in checks), "checks": checks,
              "method": "Real React 19 StrictMode hook in Chromium; explicitly controlled HTTP responses and response ordering; no production browser or backend data modified",
              "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in ("src/hooks/usePlanner.ts", "src/lib/planner-context.ts")}}
    (ROOT / "artifacts/planner-hook-race-verification.json").write_text(json.dumps(report, indent=2))
    print(f"{len(checks)}/{len(checks)} hook contract checks passed")


if __name__ == "__main__":
    main()
