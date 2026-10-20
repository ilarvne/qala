#!/usr/bin/env python3
"""Exercise the actual React source-profile hook using controlled HTTP only.

No production API, paid provider, corpus, preference memory or browser session is
used. This proves request/lifecycle behavior; fixture ratings are not POI data.
"""
from __future__ import annotations

import functools
import hashlib
import http.server
import json
from pathlib import Path
import subprocess
import tempfile
import threading

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CHECKS = []
IDS = ["osm-node-10001", "osm-node-10002", "osm-node-10003", "osm-node-10004"]
HARNESS = r'''
import React from "react";
import {createRoot} from "react-dom/client";
import {usePlaceProfiles} from "./src/hooks/usePlaceProfiles";
const transport = window.__transport = {requests: [], errors: [], ignoreAbort: false, maxActive: 0};
window.fetch = (input, init = {}) => new Promise((resolve, reject) => {
  const entry = {id: transport.requests.length, path: String(input), cache: init.cache, pending: true, aborted: false, ignoreAbort: transport.ignoreAbort};
  entry.respond = (data, status = 200) => {entry.pending = false; resolve(new Response(JSON.stringify(data), {status, headers:{"Content-Type":"application/json"}}));};
  if (init.signal) init.signal.addEventListener("abort", () => {
    entry.aborted = true;
    if (!entry.ignoreAbort) {entry.pending = false; reject(new DOMException("Aborted", "AbortError"));}
  }, {once:true});
  transport.requests.push(entry);
  transport.maxActive = Math.max(transport.maxActive, transport.requests.filter(r => r.pending && !r.aborted).length);
});
const realTimeout = window.setTimeout.bind(window), realClearTimeout = window.clearTimeout.bind(window);
let nextTimer = -1;
const timers = new Map();
window.setTimeout = (callback, delay, ...args) => delay === 20000 ? (timers.set(--nextTimer, () => callback(...args)), nextTimer) : realTimeout(callback, delay, ...args);
window.clearTimeout = id => timers.has(id) ? timers.delete(id) : realClearTimeout(id);
window.__fireTimeouts = () => {const active = [...timers.values()];timers.clear();active.forEach(run => run());};
function Probe() {
  const [language, setLanguage] = React.useState("ru");
  const hook = usePlaceProfiles(language);
  window.__hook = hook; window.__setLanguage = setLanguage;
  window.__state = {language, profiles: hook.profiles, pending: hook.pending};
  return React.createElement("output", null, JSON.stringify(window.__state));
}
const root = createRoot(document.getElementById("root"));
root.render(React.createElement(React.StrictMode, null, React.createElement(Probe)));
window.__unmount = () => root.unmount();
window.__invoke = (method, ...args) => {const value = window.__hook[method](...args);if (value?.catch) value.catch(error => transport.errors.push(error.message));};
window.__loadWithSignal = ids => {window.__external = new AbortController();window.__invoke("load", ids, {signal:window.__external.signal});};
'''


def check(name, condition):
    CHECKS.append({"check": name, "passed": bool(condition)})
    print(("PASS " if condition else "FAIL ") + name, flush=True)
    assert condition, name


def response(name="Fixture source", rating=4.9, rating_count=100, review_count=20):
    url = "https://2gis.kz/astana/firm/70000001018608940"
    return {"status": "matched", "checked_at": "2026-10-20T00:00:00Z", "cached": False,
            "source": {"provider": "2gis", "provider_id": "70000001018608940", "name": name, "url": url,
                       "lat": 51.118, "lon": 71.469, "address": None, "rating": rating,
                       "rating_count": rating_count, "review_count": review_count, "schedule": {},
                       "contacts": [], "rubrics": [], "has_photos": False, "route_url": None,
                       "photo_gallery_url": url + "/tab/photos", "review_url": url + "/tab/reviews"},
            "candidates": []}


def open_page(browser, base):
    context = browser.new_context()
    page = context.new_page()
    page.goto(base, wait_until="domcontentloaded")
    page.wait_for_function("window.__hook && window.__state")
    return context, page


def call(page, method, *args):
    page.evaluate("({method,args}) => window.__invoke(method,...args)", {"method": method, "args": list(args)})


def requests(page):
    return page.evaluate("window.__transport.requests.map(({id,path,cache,pending,aborted})=>({id,path,cache,pending,aborted}))")


def respond(page, identifier, value, status=200):
    page.evaluate("({identifier,value,status})=>window.__transport.requests[identifier].respond(value,status)", {"identifier": identifier, "value": value, "status": status})


def wait_count(page, count):
    page.wait_for_function("count=>window.__transport.requests.length===count", arg=count)


def limits_and_current_view(browser, base):
    context, page = open_page(browser, base)
    try:
        check("StrictMode mount performs zero provider fetches", requests(page) == [])
        call(page, "load", [IDS[0], IDS[0], IDS[1], IDS[2], IDS[3], "../invalid"])
        wait_count(page, 2)
        check("explicit load starts at most two concurrent requests", len(requests(page)) == 2)
        check("all requests bypass browser caches", all(row["cache"] == "no-store" for row in requests(page)))
        respond(page, 0, response())
        wait_count(page, 3)
        respond(page, 1, {"status": "ambiguous", "source": None, "candidates": [], "checked_at": None})
        respond(page, 2, response(rating=0, rating_count=0, review_count=None))
        page.wait_for_function("!window.__state.pending")
        profiles = page.evaluate("window.__state.profiles")
        check("IDs are deduplicated and capped at three", set(profiles) == set(IDS[:3]) and len(requests(page)) == 3)
        check("transport concurrency never exceeds two", page.evaluate("window.__transport.maxActive") == 2)
        source = profiles[IDS[0]]["result"]["source"]
        check("rating votes and written-review counts remain separate", source["rating_count"] == 100 and source["review_count"] == 20)
        check("ambiguous results do not become a matched rating", profiles[IDS[1]]["result"]["status"] == "ambiguous" and profiles[IDS[1]]["result"]["source"] is None)
        zero = profiles[IDS[2]]["result"]["source"]
        check("zero survives while missing review counts stay null", zero["rating"] == 0 and zero["rating_count"] == 0 and zero["review_count"] is None)
        call(page, "load", list(reversed(IDS[:3])))
        check("another consumer reuses only the currently visible profiles", len(requests(page)) == 3 and not page.evaluate("window.__state.pending"))
        call(page, "load", [IDS[0]], {"force": True})
        wait_count(page, 4)
        respond(page, 3, {"detail": "Controlled failure"}, 429)
        page.wait_for_function("!window.__state.pending")
        check("HTTP failure yields an error without a fabricated score", page.evaluate("window.__state.profiles[Object.keys(window.__state.profiles)[0]].error") == "failed")
        call(page, "load", [IDS[0]], {"force": True})
        wait_count(page, 5)
        respond(page, 4, response("Explicit retry"))
        page.wait_for_function("!window.__state.pending")
        check("an explicit retry can replace a failed current profile", page.evaluate("window.__state.profiles[Object.keys(window.__state.profiles)[0]].result.source.name") == "Explicit retry")
        check("profile fetching writes no local or session storage", page.evaluate("localStorage.length===0 && sessionStorage.length===0"))
    finally:
        context.close()


def stale_and_language(browser, base):
    context, page = open_page(browser, base)
    try:
        page.evaluate("window.__transport.ignoreAbort=true")
        call(page, "load", IDS[:3]); wait_count(page, 2)
        call(page, "load", [IDS[3]]); wait_count(page, 3)
        check("new selection aborts both superseded requests", all(row["aborted"] for row in requests(page)[:2]))
        respond(page, 2, response("Current selection"))
        page.wait_for_function("!window.__state.pending")
        respond(page, 0, response("Stale first")); respond(page, 1, response("Stale second"))
        page.wait_for_timeout(20)
        check("late aborted replies cannot overwrite the active place", page.evaluate("Object.keys(window.__state.profiles).length===1 && Object.values(window.__state.profiles)[0].result.source.name==='Current selection'"))
        check("a canceled batch never starts its queued third request", len(requests(page)) == 3)
        call(page, "load", IDS[:3]); wait_count(page, 5)
        page.evaluate("window.__setLanguage('en')")
        page.wait_for_function("window.__state.language==='en' && Object.keys(window.__state.profiles).length===0")
        respond(page, 3, response("Old language")); respond(page, 4, response("Old language"))
        page.wait_for_timeout(20)
        check("language changes discard prior profiles without automatically fetching", len(requests(page)) == 5 and page.evaluate("Object.keys(window.__state.profiles).length===0"))
        call(page, "load", [IDS[0]]); wait_count(page, 6)
        check("the next explicit request uses the selected language", requests(page)[5]["path"].endswith("language=en"))
        respond(page, 5, response()); page.wait_for_function("!window.__state.pending")
    finally:
        context.close()


def cancellation_timeout_and_unmount(browser, base):
    context, page = open_page(browser, base)
    try:
        page.evaluate("ids=>window.__loadWithSignal(ids)", IDS[:3]); wait_count(page, 2)
        page.evaluate("window.__external.abort()")
        page.wait_for_function("Object.keys(window.__state.profiles).length===0")
        check("external cancellation clears state and aborts active requests", all(row["aborted"] for row in requests(page)) and len(requests(page)) == 2)
        call(page, "load", [IDS[0]]); wait_count(page, 3)
        page.evaluate("window.__fireTimeouts()")
        page.wait_for_function("!window.__state.pending")
        check("bounded timeout becomes an actionable timeout state", page.evaluate("Object.values(window.__state.profiles)[0].error") == "timeout")
        page.evaluate("window.__transport.ignoreAbort=true")
        call(page, "load", IDS[:3]); wait_count(page, 5)
        page.evaluate("window.__unmount()")
        check("unmount aborts every active request", all(row["aborted"] for row in requests(page)[3:]))
        respond(page, 3, response("After unmount")); respond(page, 4, response("After unmount"))
        call(page, "load", [IDS[3]])
        page.wait_for_timeout(20)
        check("unmounted hook cannot restart a queued or new request", len(requests(page)) == 5)
        check("controlled cancellation produces no unhandled failures", page.evaluate("window.__transport.errors") == [])
    finally:
        context.close()


def main():
    with tempfile.TemporaryDirectory(prefix="qala-place-profiles-") as folder:
        directory = Path(folder)
        build = {"stdin": {"contents": HARNESS, "resolveDir": str(ROOT), "loader": "tsx"}, "bundle": True,
                 "format": "esm", "platform": "browser", "outfile": str(directory / "probe.js"),
                 "alias": {"@": str(ROOT / "src")}, "define": {"process.env.NODE_ENV": '"development"'}}
        subprocess.run(["node", "--input-type=module", "-e", "import {build} from 'esbuild';await build(" + json.dumps(build) + ")"], cwd=ROOT, check=True)
        (directory / "index.html").write_text('<!doctype html><html><body><main id="root"></main><script type="module" src="/probe.js"></script></body></html>')
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *_): pass
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(directory)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True, executable_path="/usr/bin/chromium", args=["--no-sandbox"])
                try:
                    base = "http://127.0.0.1:" + str(server.server_port)
                    limits_and_current_view(browser, base)
                    stale_and_language(browser, base)
                    cancellation_timeout_and_unmount(browser, base)
                finally: browser.close()
        finally: server.shutdown(); server.server_close()
    report = {"passed": all(check["passed"] for check in CHECKS), "checks": CHECKS,
              "method": "Actual React19 StrictMode hook in Chromium, controlled HTTP fixtures only; zero production provider calls. These fixture ratings are not data coverage proof.",
              "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in ("src/hooks/usePlaceProfiles.ts", "src/lib/twogis-api.ts")}}
    (ROOT / "artifacts/place-profile-hook-verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"{len(CHECKS)}/{len(CHECKS)} checks passed")


if __name__ == "__main__": main()
