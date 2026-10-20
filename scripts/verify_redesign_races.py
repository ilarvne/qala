#!/usr/bin/env python3
"""Focused production-browser checks for request races and GPS watcher ownership.

Run with /usr/bin/python3 scripts/verify_redesign_races.py. Requires the existing
system Playwright installation and a running production app/API at QALA_DEMO_URL.
API responses are real. Explicit injected boundaries are response-delivery timing,
one browser transport failure after a real response, and synthetic GPS callbacks.
No screenshots, existing browser sessions, or application source are changed.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = os.getenv("QALA_DEMO_URL", "http://127.0.0.1:8000")
REPORT = ROOT / "artifacts/redesign-races.json"
checks: list[dict] = []
evidence: dict = {}

INIT = r"""(() => {
  const state = window.__qalaRaces = {
    requests: [], responses: [], errors: [], holdMemory: HOLD_MEMORY,
    memoryHeld: false, mode: 'pass', recommendHeld: 0, releaseRecommendations: [],
  };
  let releaseMemory;
  const memoryGate = new Promise(resolve => { releaseMemory = resolve; });
  state.releaseMemory = releaseMemory;
  const originalFetch = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const path = new URL(typeof input === 'string' ? input : input.url, location.href).pathname;
    if (!path.startsWith('/api/')) return originalFetch(input, init);
    const body = init?.body ? JSON.parse(init.body) : null;
    const entry = { path, body, method: init?.method || 'GET' };
    state.requests.push(entry);
    const mode = path === '/api/recommend' ? state.mode : 'pass';
    const actualResponse = originalFetch(input, init);
    try {
      if (state.holdMemory && path.startsWith('/api/memory/')) {
        state.memoryHeld = true;
        await memoryGate;
      }
      const response = await actualResponse;
      const data = await response.clone().json();
      state.responses.push({ ...entry, status: response.status, data });
      if (mode.startsWith('hold')) {
        state.recommendHeld += 1;
        await new Promise(resolve => state.releaseRecommendations.push(resolve));
      }
      if (mode === 'hold-fail') throw new TypeError('Injected browser transport failure after real API response');
      return response;
    } catch (error) {
      state.errors.push({ path, name: error.name, message: error.message });
      throw error;
    }
  };
  let nextId = 100;
  const active = new Map();
  const gps = window.__qalaGps = {
    created: [], cleared: [],
    active: () => [...active.keys()],
    error: id => active.get(id)?.error({ code: 3, message: 'Injected GPS timeout' }),
    fix: (id, lat, lon) => active.get(id)?.success({
      coords: { latitude: lat, longitude: lon, accuracy: 8, heading: null }, timestamp: Date.now(),
    }),
  };
  Object.defineProperty(navigator, 'geolocation', { configurable: true, value: {
    getCurrentPosition() { throw new Error('This probe does not request real device location'); },
    watchPosition(success, error) {
      const id = nextId++;
      active.set(id, { success, error }); gps.created.push(id); return id;
    },
    clearWatch(id) { gps.cleared.push(id); active.delete(id); },
  } });
})();
"""


def check(name: str, condition: bool, detail=None):
    row = {"check": name, "passed": bool(condition)}
    if detail is not None:
        row["detail"] = detail
    checks.append(row)
    print(("PASS " if condition else "FAIL ") + name, flush=True)
    if not condition:
        raise AssertionError(name)


def new_page(browser, hold_memory=False):
    context = browser.new_context()
    context.add_init_script(INIT.replace("HOLD_MEMORY", str(hold_memory).lower()))
    page = context.new_page()
    page.set_default_timeout(12_000)
    page.goto(BASE, wait_until="domcontentloaded")
    page.get_by_role("combobox", name="Time available", exact=True).wait_for()
    bundle = page.locator('script[src*="/assets/index-"]').get_attribute("src")
    bundles = evidence.setdefault("production_bundles", [])
    if bundle not in bundles:
        bundles.append(bundle)
    return context, page


def choose_time(page, minutes):
    page.get_by_role("combobox", name="Time available", exact=True).click()
    page.get_by_role("option", name=f"{minutes} min", exact=True).click()


def settled(page):
    page.wait_for_function("!document.querySelector('.map-status')", timeout=25_000)


def street_ready(page):
    page.wait_for_function("document.querySelector('.route-quality')?.textContent.includes('Street route')", timeout=30_000)
    settled(page)


def open_route(page):
    if not page.locator(".route-sheet").is_visible():
        page.locator('.app-rail button[aria-label="Walking itinerary"]').click()
    page.locator(".route-sheet").wait_for()


def all_instruction_buttons_disabled(page):
    buttons = page.locator(".all-directions button")
    return buttons.count() > 0 and buttons.evaluate_all("buttons => buttons.every(button => button.disabled)")


def startup_race(browser):
    context, page = new_page(browser, hold_memory=True)
    try:
        page.wait_for_function("window.__qalaRaces.memoryHeld")
        choose_time(page, 90)
        choose_time(page, 45)
        page.wait_for_function("window.__qalaRaces.responses.some(r => r.path === '/api/recommend' && r.body.duration_minutes === 45)")
        settled(page)
        page.evaluate("window.__qalaRaces.releaseMemory()")
        page.wait_for_function("window.__qalaRaces.responses.some(r => r.path.startsWith('/api/memory/'))")
        page.wait_for_timeout(450)
        bodies = page.evaluate("window.__qalaRaces.requests.filter(r => r.path === '/api/recommend').map(r => ({duration:r.body.duration_minutes, language:r.body.language}))")
        check("delayed real memory response cannot launch obsolete default plan", [body["duration"] for body in bodies] == [90, 45], bodies)
        check("rapid settings retain the latest duration after bootstrap resolves", "45 min" in page.get_by_role("combobox", name="Time available", exact=True).inner_text())
        names = page.evaluate("window.__qalaRaces.responses.filter(r => r.path === '/api/recommend' && r.body.duration_minutes === 45).at(-1).data.recommendations.map(p => p.name)")
        check("visible stops match the latest real recommendation response", page.locator(".place-card h3").all_text_contents() == names, names)
        evidence["startup_recommendation_requests"] = bodies
    finally:
        context.close()


def route_guards_and_gps(browser):
    context, page = new_page(browser)
    try:
        street_ready(page)
        check("fresh real street route can start", page.locator(".start-walk").is_enabled())
        route = page.evaluate("window.__qalaRaces.responses.filter(r => r.path === '/api/navigation/route').at(-1).data")
        navigation_request = page.evaluate("window.__qalaRaces.requests.filter(r => r.path === '/api/navigation/route').at(-1).body")
        check("duplicate origin and first stop are removed before real routing", len(navigation_request["coordinates"]) == 2 and navigation_request["coordinates"][0] != navigation_request["coordinates"][1])
        open_route(page)
        check("origin stop displays zero walking without stealing the next leg", "0 min walking to this stop" in page.locator(".route-stops li").first.inner_text() and "0 min walking to this stop" not in page.locator(".route-stops li").nth(1).inner_text())
        page.keyboard.press("Escape")

        page.evaluate("window.__qalaRaces.mode = 'hold-fail'")
        choose_time(page, 90)
        page.wait_for_function("window.__qalaRaces.recommendHeld === 1")
        check("main start is disabled while changed settings await a real response", page.locator(".start-walk").is_disabled())
        open_route(page)
        check("route start and every instruction are disabled during replacement", page.locator(".route-actions button").first.is_disabled() and all_instruction_buttons_disabled(page))
        page.evaluate("window.__qalaRaces.releaseRecommendations.splice(0).forEach(release => release())")
        page.wait_for_function("document.querySelector('.map-status.error')?.textContent.includes('Connection lost')")
        check("failed replacement cannot revive an itinerary from the old context", page.locator(".start-walk").is_disabled() and page.locator(".route-actions button").first.is_disabled() and all_instruction_buttons_disabled(page))
        page.keyboard.press("Escape")
        page.evaluate("window.__qalaRaces.mode = 'pass'")
        choose_time(page, 60)
        street_ready(page)
        open_route(page)
        page.locator(".route-actions button").first.click()
        page.get_by_role("button", name="Use live location", exact=True).click()
        first = page.evaluate("window.__qalaGps.created.at(-1)")
        check("explicit live-location action owns one synthetic watcher", page.evaluate("window.__qalaGps.active()") == [first])
        page.evaluate("id => window.__qalaGps.error(id)", first)
        page.get_by_role("button", name="Use live location", exact=True).wait_for()
        check("GPS timeout clears the active watcher before offering retry", page.evaluate("window.__qalaGps.active().length === 0 && window.__qalaGps.cleared.includes(window.__qalaGps.created[0])"))
        page.get_by_role("button", name="Use live location", exact=True).click()
        second = page.evaluate("window.__qalaGps.created.at(-1)")
        check("retry creates a fresh watcher with sole ownership", second != first and page.evaluate("window.__qalaGps.active()") == [second])
        lon, lat = route["geometry"]["coordinates"][0]
        page.evaluate("({id,lat,lon}) => window.__qalaGps.fix(id,lat,lon)", {"id": second, "lat": lat, "lon": lon})
        check("fresh watcher callback reaches the navigation UI", "Following your location" in page.locator(".walking-navigation").inner_text())
        route_steps = [step for leg in route["legs"] for step in leg["steps"]]
        target, target_step = max(enumerate(route_steps[1:-1], start=1), key=lambda item: item[1]["geometry_end_index"] - item[1]["geometry_start_index"])
        geometry_index = (target_step["geometry_start_index"] + target_step["geometry_end_index"]) // 2
        lon, lat = route["geometry"]["coordinates"][geometry_index]
        page.evaluate("({id,lat,lon}) => window.__qalaGps.fix(id,lat,lon)", {"id": second, "lat": lat, "lon": lon})
        page.wait_for_function("target => Number(document.querySelector('.turn-heading span')?.textContent.match(/Step (\\d+)/)?.[1]) >= target", arg=target + 1)
        advanced_step = page.locator(".turn-heading span").inner_text()
        check("synthetic mid-route fix advances the UI across missed real-route turns", int(advanced_step.split()[1]) >= target + 1, advanced_step)
        lon, lat = route["geometry"]["coordinates"][0]
        page.evaluate("({id,lat,lon}) => window.__qalaGps.fix(id,lat,lon)", {"id": second, "lat": lat, "lon": lon})
        page.wait_for_timeout(100)
        check("a synthetic backwards fix cannot reverse the UI instruction", page.locator(".turn-heading span").inner_text() == advanced_step)
        page.get_by_role("button", name="End navigation", exact=True).click()
        check("ending navigation clears the fresh watcher without orphaning the old one", page.evaluate("window.__qalaGps.active().length === 0 && window.__qalaGps.created.every(id => window.__qalaGps.cleared.includes(id))"))
        evidence["gps_watcher_ownership"] = page.evaluate("({created: window.__qalaGps.created, cleared: window.__qalaGps.cleared, active: window.__qalaGps.active()})")
        evidence["real_initial_route"] = {key: route[key] for key in ("provider", "distance_m", "duration_seconds", "warnings")}

        page.keyboard.press("Escape")
        page.get_by_role("combobox", name="Language", exact=True).click()
        page.get_by_role("option", name="KZ", exact=True).click()
        page.wait_for_function("window.__qalaRaces.responses.some(r => r.path === '/api/navigation/route' && r.body.language === 'kk')", timeout=30_000)
        street_ready(page)
        open_route(page)
        warnings = page.evaluate("window.__qalaRaces.responses.filter(r => r.path === '/api/navigation/route' && r.body.language === 'kk').at(-1).data.warnings")
        check("actual router fallback warnings render visibly before start controls", bool(warnings) and all(
            page.locator(".route-warning").filter(has_text=warning).is_visible() and
            page.locator(".route-warning").filter(has_text=warning).evaluate("node => Boolean(node.compareDocumentPosition(document.querySelector('.route-actions')) & Node.DOCUMENT_POSITION_FOLLOWING)")
            for warning in warnings
        ), warnings)
        evidence["real_router_warnings"] = warnings
    finally:
        context.close()


def main():
    failures = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=os.getenv("QALA_CHROME", "/usr/bin/chromium"), args=["--no-sandbox", "--disable-dev-shm-usage", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        try:
            for probe in (startup_race, route_guards_and_gps):
                try:
                    probe(browser)
                except Exception as error:
                    failures.append({"probe": probe.__name__, "error": str(error)})
                    print(f"FAIL {probe.__name__}: {error}", flush=True)
        finally:
            browser.close()
    report = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE,
        "method": "Separate headless Chromium context via existing system Python Playwright; production frontend and real FastAPI responses.",
        "injected_boundaries": ["Actual memory-response delivery held until after rapid UI settings changes", "Actual recommendation-response delivery held, then browser TypeError injected to exercise request failure", "Synthetic browser geolocation watcher callbacks and timeout; no real device GPS"],
        "coverage_limits": ["No naturally over-budget real street route was encountered; instruction gates were checked during pending and failed context replacement instead", "Kazakh fallback warning exercised with the real router response; no invented snap warnings or provider timings", "No actual walk, provider phone call, screenshots or visual design approval"],
        "checks": checks,
        "passed": sum(check["passed"] for check in checks),
        "total": len(checks),
        "failures": failures,
        "evidence": evidence,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"{report['passed']}/{report['total']} focused browser checks passed; {len(failures)} probe failures", flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
