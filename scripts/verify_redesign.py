#!/usr/bin/env python3
"""Exercise the built v2 app with a real browser, API, vector map and router."""
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("QALA_BROWSER_SESSION", "qala-v2")
from capture_demo import ab, js, ROOT, BASE_URL

OUT = ROOT / ".impeccable/review"
OUT.mkdir(parents=True, exist_ok=True)
checks = []


def check(name, passed):
    checks.append({"check": name, "passed": bool(passed)})
    print(("PASS " if passed else "FAIL ") + name, flush=True)


def settled():
    ab("wait", "--fn", 'document.querySelectorAll(".place-card").length > 0 && document.querySelectorAll(".citymap-place-marker").length > 0 && !document.querySelector(".citymap-loading")')
    ab("wait", "--fn", 'document.querySelector(".route-quality")?.textContent.includes("Street route")')


def no_captions():
    return js('!["Astana, at your pace.","Source-backed places. Your preferences, your choice.","Your location. Your control.","Your exact location and messages stay out"].some(t=>document.body.textContent.includes(t)) && !document.querySelector(".planned-caption")')


def main():
    ab("set", "viewport", "1440", "960")
    ab("open", BASE_URL)
    settled()
    check("actual vector map loads with clickable place markers", js('document.querySelectorAll(".citymap-place-marker").length') > 0)
    check("default street routing handles starting at the first POI", js('document.querySelector(".route-quality").textContent.includes("Street route")'))
    check("removed decorative captions stay absent", no_captions())
    check("new artwork loads from project files", js('document.querySelector(".qa-city-image img")?.naturalWidth > 100'))
    check("desktop document has no horizontal overflow", js('document.documentElement.scrollWidth <= innerWidth'))
    ab("screenshot", str(OUT / "desktop.png"))
    check("embedded map opens in 3D without a provider key", js('document.querySelector(".citymap-scene")?.dataset.mapDepth === "3d"'))
    ab("click", '[aria-label="Switch to 2D map"]')
    ab("wait", '[aria-label="Switch to 3D map"]')
    flat_state = r'''(() => {
      const el=document.querySelector('.citymap-renderer');
      const key=Object.keys(el).find(k=>k.startsWith('__reactFiber'));
      for(let f=el[key];f;f=f.return) for(let h=f.memoizedState;h;h=h.next){
        const m=h.memoizedState?.current;
        if(typeof m?.getPitch==='function' && typeof m?.getMaxPitch==='function')
          return m.getPitch()===0 && m.getMaxPitch()===0 && m.getStyle().layers.every(l=>l.type!=='fill-extrusion'||m.getLayoutProperty(l.id,'visibility')==='none');
      }
      return false;
    })()'''
    check("2D hides all depth and locks camera flat", js(flat_state))
    ab("screenshot", str(OUT / "flat-map.png"))
    ab("click", '[aria-label="Switch to 3D map"]')
    ab("wait", '[aria-label="Switch to 2D map"]')
    check("3D control remains embedded", js('!document.querySelector("a.citymap-external-3d,iframe,.citymap-provider-help")'))
    ab("click", ".citymap-place-marker:nth-of-type(1)")
    check("map marker selection is interactive", js('document.querySelectorAll(".citymap-place-marker[aria-pressed=true]").length') == 1)
    ab("find", "role", "button", "click", "--name", "A good coffee nearby", "--exact")
    ab("wait", ".qa-plan")
    ab("wait", "--fn", 'document.querySelectorAll(".qa-stop").length>0 && document.querySelectorAll(".place-card").length===1')
    settled()
    check("Assistant UI sends a real request and renders its tool result", js('document.querySelectorAll(".qa-user-message").length===1 && document.querySelectorAll(".qa-stop").length===1'))
    check("assistant result updates map and place cards", js('document.querySelector(".qa-stop-name span").textContent===document.querySelector(".place-name h3").textContent'))
    check("assistant and itinerary use the same routed total", js(r'Number(document.querySelector(".qa-plan-duration").textContent.match(/\d+/)[0])===Number(document.querySelector(".itinerary-title span").textContent.match(/· (\d+) min/)[1])'))
    ab("screenshot", str(OUT / "assistant.png"))
    if not js('document.querySelector(".place-save").getAttribute("aria-pressed")==="true"'):
        ab("click", ".place-save")
    ab("click", '[aria-label="Saved places"]')
    ab("wait", "[role=dialog]")
    check("saved collection contains the actual recommended place", js('Array.from(document.querySelectorAll(".saved-place strong")).some(el=>el.textContent===document.querySelector(".place-card h3").textContent)'))
    ab("press", "Escape")
    ab("click", '[data-testid^="source-button-"]')
    ab("wait", "[role=dialog]")
    check("source inspector links actual POI evidence", js('Boolean(document.querySelector(".evidence-links a[href*=openstreetmap]"))'))
    ab("press", "Escape")
    ab("click", ".start-walk")
    ab("wait", ".walking-navigation")
    check("walking navigation presents real street instructions", js('document.querySelector(".walking-navigation h3").textContent.length > 5'))
    old_instruction = js('document.querySelector(".walking-navigation h3").textContent')
    ab("find", "role", "button", "click", "--name", "Next turn", "--exact")
    check("next-turn control advances the instruction", js('document.querySelector(".walking-navigation h3").textContent') != old_instruction)
    ab("download", ".route-actions button:nth-child(2)", str(ROOT / "artifacts/qala-walking-route.gpx"))
    check("GPX export contains real street geometry", "<trkpt " in (ROOT / "artifacts/qala-walking-route.gpx").read_text())
    ab("screenshot", str(OUT / "navigation.png"))
    ab("press", "Escape")
    ab("set", "viewport", "1280", "900")
    check("1280px layout has no document overflow", js('document.documentElement.scrollWidth <= innerWidth'))
    ab("set", "viewport", "390", "844")
    ab("reload")
    settled()
    check("mobile document has no horizontal overflow", js('document.documentElement.scrollWidth <= innerWidth'))
    check("mobile map and walking control are visible", js('getComputedStyle(document.querySelector(".map-stage")).visibility==="visible" && document.querySelector(".start-walk").getBoundingClientRect().bottom < innerHeight'))
    check("removed captions stay absent on mobile", no_captions())
    ab("screenshot", str(OUT / "mobile.png"))
    ab("click", '[aria-label="Assistant"]')
    check("mobile assistant opens without leaving the page", js('getComputedStyle(document.querySelector(".assistant-pane")).display') == "flex")
    ab("screenshot", str(OUT / "mobile-assistant.png"))
    report = {"method": "agent-browser 0.27.0; built app, real FastAPI, OpenFreeMap vector tiles and Valhalla pedestrian route; no mocked API responses", "checks": checks, "passed": sum(c["passed"] for c in checks), "total": len(checks), "screenshots": [str(p.relative_to(ROOT)) for p in OUT.glob("*.png")]}
    (ROOT / "artifacts/redesign-browser-verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(str(report["passed"]) + "/" + str(report["total"]) + " redesign browser checks passed", flush=True)
    if report["passed"] != report["total"]: sys.exit(1)


if __name__ == "__main__":
    main()
