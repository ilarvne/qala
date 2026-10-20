#!/usr/bin/env python3
# Historical keyed-provider harness, superseded by scripts/verify_embedded_map.py.
"""Verify invalid-key recovery in the full production app.

Build an isolated frontend with a deliberately invalid synthetic Yandex key and
serve it with Vite preview (API proxy enabled). Set QALA_DEMO_URL to its URL.
This checks rejection and fallback, never a successful authorized 3D session.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QALA_BROWSER_SESSION", "qala-yandex-invalid-app")
os.environ.setdefault("QALA_DEMO_URL", "http://127.0.0.1:5174")
from capture_demo import ab, js, BASE_URL, ROOT

checks = []


def check(name, passed):
    checks.append({"name": name, "passed": bool(passed)})
    print(("PASS " if passed else "FAIL ") + name, flush=True)
    if not passed:
        raise AssertionError(name)


def flat_state():
    return js("""(() => {
      const element = document.querySelector('.citymap-renderer');
      if (!element) return null;
      const key = Object.keys(element).find(k => k.startsWith('__reactFiber'));
      for (let fiber = element[key]; fiber; fiber = fiber.return) {
        for (let hook = fiber.memoizedState; hook; hook = hook.next) {
          const map = hook.memoizedState?.current;
          if (typeof map?.getPitch !== 'function') continue;
          const data = map.getSource('qala-route')?._data;
          const feature = data?.geojson ?? data;
          return {
            pitch: map.getPitch(), maxPitch: map.getMaxPitch(),
            points: feature?.geometry?.coordinates?.length ?? 0,
            extrusions: map.getStyle().layers.filter(layer =>
              layer.type === 'fill-extrusion' &&
              map.getLayoutProperty(layer.id, 'visibility') !== 'none').length
          };
        }
      }
      return null;
    })()""")


def main():
    error = None
    state = None
    try:
        ab("set", "viewport", "1280", "720")
        ab("open", BASE_URL)
        ab("wait", "--fn", 'document.querySelectorAll(".place-card").length===2 && document.querySelector(".route-quality")?.textContent.includes("Street route")')
        ab("wait", "--fn", 'Boolean(document.querySelector(".citymap-fallback[role=alert]"))')
        check("Actual invalid-key production app offers recovery", js('document.querySelector(".citymap-fallback").textContent.includes("Yandex")'))
        check("Unavailable native controls are disabled", js('Array.from(document.querySelectorAll(".citymap-controls button")).slice(0,5).every(button=>button.disabled)'))
        total = js('document.querySelector(".itinerary-title span").textContent')
        ab("click", ".place-card:nth-child(2) .place-name")
        selected = js('document.querySelector(".place-card.selected").dataset.placeId')
        ab("find", "role", "button", "click", "--name", "Use 2D map", "--exact")
        ab("wait", "--fn", 'document.querySelectorAll(".citymap-place-marker").length===2 && !document.querySelector(".citymap-loading")')
        state = flat_state()
        check("Actual pointer fallback loads one true-flat renderer", state and state["pitch"] == 0 and state["maxPitch"] == 0 and state["extrusions"] == 0 and js('document.querySelectorAll("canvas").length') == 1)
        check("Exact Valhalla route and totals survive fallback", state["points"] > 40 and js('document.querySelector(".itinerary-title span").textContent') == total)
        check("Selected card and numbered marker survive fallback", js('document.querySelector(".place-card.selected").dataset.placeId') == selected and js('document.querySelector(".citymap-place-marker[aria-pressed=true]").textContent') == "2")
        ab("click", '[aria-label="Switch to 3D map"]')
        ab("wait", "--fn", 'Boolean(document.querySelector(".citymap-fallback[role=alert]"))')
        check("Reconnect removes the flat canvas before failed native attempt", js('document.querySelectorAll("canvas").length') == 0)
        # Cached rejection can complete between browser polls. Observe the new
        # SDK attempt instead of depending on a transient loading frame.
        js('window.__qalaRetryLoads=0; window.__qalaRetryObserver=new MutationObserver(records=>records.forEach(record=>record.addedNodes.forEach(node=>{if(node instanceof HTMLScriptElement&&node.dataset.qalaYandexSdk)window.__qalaRetryLoads++}))); window.__qalaRetryObserver.observe(document.head,{childList:true}); true')
        ab("find", "role", "button", "click", "--name", "Try again", "--exact")
        ab("wait", "--fn", 'window.__qalaRetryLoads>0 && Boolean(document.querySelector(".citymap-fallback[role=alert]"))')
        js('window.__qalaRetryObserver.disconnect(); true')
        check("Native retry makes a new SDK attempt and preserves the plan", js('document.querySelector(".itinerary-title span").textContent') == total and js('document.querySelector(".place-card.selected").dataset.placeId') == selected)
        ab("find", "role", "button", "click", "--name", "Use 2D map", "--exact")
        ab("wait", "--fn", 'document.querySelectorAll(".citymap-place-marker").length===2 && !document.querySelector(".citymap-loading")')
        check("Repeated fallback has one canvas and no failed SDK script", js('document.querySelectorAll("canvas").length===1 && document.querySelectorAll("script[data-qala-yandex-sdk]").length===0 && !document.querySelector("iframe")'))
        check("Excluded provider and municipal requests stay absent", js('!performance.getEntriesByType("resource").some(resource=>{try{return /2gis|gis\\.esaulet/.test(new URL(resource.name).hostname)}catch{return false}})'))
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        report = {
            "kind": "Actual full production frontend with deliberately invalid synthetic Yandex key; real API, map tiles and Valhalla route",
            "checks": checks, "passed": sum(row["passed"] for row in checks),
            "planned_checks": 9, "executed_checks": len(checks), "error": error,
            "valid_owned_key_3d_verified": False, "route_state": state,
        }
        (ROOT / "artifacts/yandex-app-recovery-verification.json").write_text(json.dumps(report, indent=2) + "\n")
        ab("close")
    if error:
        raise SystemExit(error)


if __name__ == "__main__":
    main()
