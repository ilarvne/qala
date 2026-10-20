#!/usr/bin/env python3
"""Focused browser proof for the embedded keyless MapLibre 3D/2D map.

Requires a production frontend and real API at QALA_DEMO_URL (default :8000).
Uses agent-browser 0.27.0. No recommendation, tile, or routing responses are
mocked. Geolocation callbacks are synthetic and clearly separated in the report.
Screenshots are a single desktop/mobile batch plus optional focused confirmation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys

os.environ.setdefault("QALA_BROWSER_SESSION", "qala-embedded-map")
from capture_demo import ab, js, ROOT, BASE_URL, CMD

# Optional already-installed binary avoids repeated npx startup during local QA.
if os.getenv("QALA_AGENT_BROWSER_BIN"):
    CMD[:] = [os.environ["QALA_AGENT_BROWSER_BIN"], "--session", os.environ["QALA_BROWSER_SESSION"]]

REPORT = ROOT / "artifacts/embedded-map-verification.json"
CHECKS: list[dict] = []
EVIDENCE: dict = {}

MAP = r"""(() => {
  const el = document.querySelector('.citymap-renderer');
  if (!el) return null;
  const key = Object.keys(el).find(key => key.startsWith('__reactFiber'));
  for (let fiber = el[key]; fiber; fiber = fiber.return) {
    for (let hook = fiber.memoizedState; hook; hook = hook.next) {
      const candidate = hook.memoizedState?.current;
      if (typeof candidate?.getPitch === 'function' && typeof candidate?.getStyle === 'function') return candidate;
    }
  }
  return null;
})()"""

BIND = "(window.__embeddedMap = " + MAP + ", Boolean(window.__embeddedMap))"

STATE = r"""(() => {
  const map = window.__embeddedMap;
  if (!map) return null;
  const layers = map.getStyle().layers;
  return {
    pitch: map.getPitch(), maxPitch: map.getMaxPitch(), bearing: map.getBearing(), zoom: map.getZoom(),
    center: map.getCenter().toArray(),
    depthLayers: layers.filter(layer => layer.type === 'fill-extrusion' || layer.type === 'model' || layer.type === 'custom').map(layer => ({
      id: layer.id, type: layer.type, visibility: map.getLayoutProperty(layer.id, 'visibility') ?? 'visible',
    })),
    canvasCount: document.querySelectorAll('.citymap-renderer canvas').length,
    sameCanvas: window.__embeddedCanvas === map.getCanvas(),
    selected: document.querySelector('.citymap-place-marker[aria-pressed=true]')?.closest('[data-place-id]')?.dataset.placeId,
    route: map.getSource('qala-route')?.serialize?.().data ?? map.getSource('qala-route')?._data,
  };
})()"""

BUILDINGS = r"""(() => {
  const map = window.__embeddedMap;
  const layers = map.getStyle().layers.filter(layer => layer.type === 'fill-extrusion');
  const heights = layers.flatMap(layer => {
    const value = map.style.getLayer(layer.id).paint.get('fill-extrusion-height');
    return map.queryRenderedFeatures(undefined, { layers: [layer.id] }).map(feature => Number(value.evaluate(feature, {})));
  }).filter(Number.isFinite);
  return { zoom: map.getZoom(), featureCount: heights.length, positiveHeightCount: heights.filter(height => height > .1).length, maximumHeight: Math.max(0,...heights) };
})()"""

GET_PROPS = r"""(() => {
  const el = document.querySelector('.citymap-renderer');
  const key = Object.keys(el).find(key => key.startsWith('__reactFiber'));
  for (let fiber = el[key]; fiber; fiber = fiber.return) {
    if (fiber.memoizedProps?.navigation?.street_routed) return {
      navigation: fiber.memoizedProps.navigation,
      selectedId: fiber.memoizedProps.selectedId,
      location: fiber.memoizedProps.location,
    };
  }
  return null;
})()"""

GPS = r"""(() => {
  let next = 700;
  const active = new Map();
  window.__embeddedGps = {
    created: [], cleared: [], active: () => [...active.keys()],
    fix: (lat, lon, heading = 65) => [...active.values()].forEach(watcher => watcher.success({
      coords: { latitude: lat, longitude: lon, accuracy: 8, heading }, timestamp: Date.now(),
    })),
  };
  Object.defineProperty(navigator, 'geolocation', { configurable: true, value: {
    getCurrentPosition() { throw new Error('No actual device GPS requested by this verification'); },
    watchPosition(success, error) {
      const id = next++;
      active.set(id, { success, error }); window.__embeddedGps.created.push(id); return id;
    },
    clearWatch(id) { window.__embeddedGps.cleared.push(id); active.delete(id); },
  }});
  return true;
})()"""


def check(name: str, passed: bool, detail=None):
    entry = {"check": name, "passed": bool(passed)}
    if detail is not None:
        entry["detail"] = detail
    CHECKS.append(entry)
    print(("PASS " if passed else "FAIL ") + name, flush=True)
    if not passed:
        raise AssertionError(name)


def settled():
    ab("wait", "--fn", 'document.querySelectorAll(".place-card").length > 0 && document.querySelectorAll(".citymap-place-marker").length > 0 && !document.querySelector(".citymap-loading")')
    ab("wait", "--fn", 'document.querySelector(".route-quality")?.textContent.includes("Street route")')
    ab("wait", "--fn", "Boolean(" + MAP + ")")
    js(BIND)
    js("window.__embeddedCanvas = window.__embeddedMap.getCanvas(); true")
    ab("wait", "--fn", "window.__embeddedMap.loaded() && !window.__embeddedMap.isMoving()")


def wait_camera():
    ab("wait", "--fn", "!window.__embeddedMap.isMoving()")


def mode_button(mode: str) -> str:
    return '[aria-label="Switch to ' + mode + ' map"]'


def no_overflow() -> bool:
    return js("document.documentElement.scrollWidth <= innerWidth")


def one_canvas() -> bool:
    state = js(STATE)
    return state["canvasCount"] == 1 and state["sameCanvas"]


def exact_route():
    props = js(GET_PROPS)
    data = js(STATE)["route"]
    data = (data or {}).get("geojson", data)
    coordinates = (data or {}).get("geometry", {}).get("coordinates")
    return bool(props and props["navigation"]["street_routed"] and coordinates == props["navigation"]["geometry"]["coordinates"])


def attribution_state():
    return js(r"""(() => {
      const node=document.querySelector('.maplibregl-ctrl-attrib');
      const cards=document.querySelector('.map-bottom');
      if(!node||!cards)return {clear:false,links:[]};
      const r=node.getBoundingClientRect();
      const links=Array.from(node.querySelectorAll('a')).map(a=>{
        const boxes=Array.from(a.getClientRects());
        const accessible=boxes.some(box=>{
          if(box.width<=0||box.height<=0)return false;
          const at=document.elementFromPoint(box.x+box.width/2,box.y+box.height/2);
          return at===a||a.contains(at);
        });
        return {label:a.textContent,href:a.href,accessible};
      });
      return {clear:r.bottom<=cards.getBoundingClientRect().top,links,rect:{x:r.x,y:r.y,width:r.width,height:r.height}};
    })()""")


def marker_clearance():
    return js(r"""(() => {
      const label=document.querySelector('.citymap-place-label');
      if(!label)return {overlap:false};
      const r=label.getBoundingClientRect();
      const controls=Array.from(document.querySelectorAll('.citymap-controls .citymap-control-group')).map(group=>group.getBoundingClientRect());
      return {overlap:controls.some(c=>r.left<c.right&&r.right>c.left&&r.top<c.bottom&&r.bottom>c.top),label:{x:r.x,y:r.y,width:r.width,height:r.height},controlLeft:Math.min(...controls.map(c=>c.left))};
    })()""")


def control_pointer_checks():
    before = js(STATE)["zoom"]
    ab("click", '[aria-label="Zoom in"]')
    wait_camera()
    check("zoom in responds to an actual pointer click", js(STATE)["zoom"] > before + .5)
    ab("click", '[aria-label="Zoom out"]')
    wait_camera()
    check("zoom out returns to the previous zoom", abs(js(STATE)["zoom"] - before) < .02)
    js("window.__embeddedMap.jumpTo({bearing: 36}); true")
    ab("click", '[aria-label="Reset bearing to north"]')
    wait_camera()
    check("compass resets a rotated map to north", abs(js(STATE)["bearing"]) < .01)
    before_center = js(STATE)["center"]
    js("window.__embeddedMap.jumpTo({center: [71.48,51.17]}); true")
    ab("click", '[aria-label="Back to your location"]')
    wait_camera()
    after = js(STATE)["center"]
    check("location control recenters inside the embedded renderer", abs(after[0] - 71.48) > .001 and abs(after[1] - 51.17) > .001, {"before": before_center, "after": after})


def desktop(shots: Path):
    ab("set", "viewport", "1440", "960")
    ab("open", BASE_URL)
    settled()
    initial = js(STATE)
    EVIDENCE["production_bundle"] = js("document.querySelector('script[src*=\"/assets/index-\"]')?.getAttribute('src')")
    EVIDENCE["desktop_initial"] = initial
    check("default view is embedded 3D with one live MapLibre canvas", initial["pitch"] >= 30 and initial["maxPitch"] > 0 and initial["canvasCount"] == 1)
    check("3D building layers are visible", any(layer["visibility"] != "none" for layer in initial["depthLayers"]), initial["depthLayers"])
    rendered_buildings = js(BUILDINGS)
    EVIDENCE["desktop_buildings"] = rendered_buildings
    check("the visible viewport contains buildings with positive evaluated 3D heights", rendered_buildings["positiveHeightCount"] > 0, rendered_buildings)
    check("3D control is a button and does not link to an external page", js("Boolean(document.querySelector('button" + mode_button("2D") + "')) && !document.querySelector('a.citymap-external-3d')"))
    check("no external provider SDK or iframe is used", js("!document.querySelector('iframe') && !performance.getEntriesByType('resource').some(r => /api-maps\\.yandex|2gis|gis\\.esaulet|cesium/i.test(r.name))"))
    check("embedded route matches real Valhalla geometry exactly", exact_route())
    props = js(GET_PROPS)
    EVIDENCE["street_route"] = {"provider": props["navigation"]["provider"], "distance_m": props["navigation"]["distance_m"], "point_count": len(props["navigation"]["geometry"]["coordinates"])}
    check("desktop has no horizontal document overflow", no_overflow())
    attribution = attribution_state()
    EVIDENCE["desktop_attribution"] = attribution
    check("desktop attribution links remain visible and pointer-accessible above the cards", attribution["clear"] and bool(attribution["links"]) and all(link["accessible"] for link in attribution["links"]), attribution)
    clearance = marker_clearance()
    EVIDENCE["desktop_marker_clearance"] = clearance
    check("desktop selected-place label clears the map controls", not clearance["overlap"], clearance)
    ab("screenshot", str(shots / "desktop-3d.png"))

    selected = initial["selected"]
    ab("click", mode_button("2D"))
    wait_camera()
    flat = js(STATE)
    check("2D is flat and locks pitch at zero", abs(flat["pitch"]) < .01 and flat["maxPitch"] == 0)
    check("2D hides every depth layer", all(layer["visibility"] == "none" for layer in flat["depthLayers"]), flat["depthLayers"])
    check("mode switch preserves canvas, selected place, and exact street geometry", one_canvas() and flat["selected"] == selected and exact_route())
    ab("screenshot", str(shots / "desktop-2d.png"))
    ab("click", mode_button("3D"))
    wait_camera()
    restored = js(STATE)
    check("actual pointer returns to 3D inside the same canvas", restored["pitch"] >= 30 and restored["sameCanvas"] and any(layer["visibility"] != "none" for layer in restored["depthLayers"]))

    js("window.__embeddedToggleDone = false; let n=0; const tick=setInterval(() => { const b=document.querySelector('.citymap-controls button[aria-label=\"Switch to 2D map\"], .citymap-controls button[aria-label=\"Switch to 3D map\"]'); b?.dispatchEvent(new MouseEvent('click', {bubbles:true, detail:1})); if(++n===12){clearInterval(tick);window.__embeddedToggleDone=true;} },25); true")
    ab("wait", "--fn", "window.__embeddedToggleDone && !window.__embeddedMap.isMoving()")
    stress = js(STATE)
    check("12 interrupting mode toggles keep one canvas and a coherent final 3D state", one_canvas() and stress["pitch"] >= 30 and stress["maxPitch"] > 0 and exact_route())
    control_pointer_checks()

    if js('document.querySelectorAll(".citymap-place-marker").length') > 1:
        selector = ".citymap-place-anchor:last-of-type .citymap-place-marker"
        # Select a concrete observed node; MapLibre has an extra origin marker.
        target = js("Array.from(document.querySelectorAll('.citymap-place-marker')).at(-1).parentElement.dataset.placeId")
        selector = '[data-place-id="' + target + '"] .citymap-place-marker'
        ab("focus", selector)
        ab("press", "Enter")
        check("keyboard selection retains focus on the selected map marker", js("document.activeElement?.matches('.citymap-place-marker[aria-pressed=true]') && document.activeElement.parentElement.dataset.placeId === " + json.dumps(target)))

    js(GPS)
    ab("click", ".start-walk")
    ab("wait", ".walking-navigation")
    check("walking navigation still opens with real instructions", js("document.querySelector('.walking-navigation h3').textContent.length > 5"))
    before = js("document.querySelector('.walking-navigation h3').textContent")
    ab("find", "role", "button", "click", "--name", "Next turn", "--exact")
    check("next-turn action advances the real route instruction", js("document.querySelector('.walking-navigation h3').textContent") != before)
    ab("find", "role", "button", "click", "--name", "Use live location", "--exact")
    check("GPS starts only from the explicit live-location action", js("window.__embeddedGps.active().length === 1 && window.__embeddedGps.created.length === 1"))
    lon, lat = props["navigation"]["geometry"]["coordinates"][0]
    js(f"window.__embeddedGps.fix({lat}, {lon}); true")
    ab("wait", ".citymap-gps")
    wait_camera()
    check("synthetic GPS updates its marker and camera without replacing the canvas", one_canvas() and js("document.querySelectorAll('.citymap-gps').length === 1") and abs(js(STATE)["center"][0] - lon) < .0001)
    ab("press", "Escape")
    ab("click", mode_button("2D"))
    wait_camera()
    check("live GPS survives switching to true flat 2D", js("document.querySelectorAll('.citymap-gps').length === 1 && window.__embeddedGps.active().length === 1") and js(STATE)["pitch"] == 0 and exact_route())
    ab("click", mode_button("3D"))
    wait_camera()
    ab("click", ".start-walk")
    ab("wait", ".walking-navigation")
    ab("find", "role", "button", "click", "--name", "End navigation", "--exact")
    check("ending navigation removes the GPS marker and clears its watcher", js("!document.querySelector('.citymap-gps') && window.__embeddedGps.active().length === 0 && window.__embeddedGps.cleared.length === 1"))
    ab("press", "Escape")
    check("map remains embedded on the original page after every control", js("location.origin === " + json.dumps(BASE_URL.rstrip('/'))) and one_canvas())
    EVIDENCE["desktop_final"] = js(STATE)


def mobile(shots: Path):
    ab("set", "viewport", "390", "844")
    ab("reload")
    settled()
    check("mobile opens the embedded 3D renderer without horizontal overflow", js(STATE)["pitch"] >= 30 and no_overflow())
    buildings = js(BUILDINGS)
    EVIDENCE["mobile_buildings"] = buildings
    check("mobile fitted route shows buildings with positive evaluated 3D heights", buildings["positiveHeightCount"] > 0, buildings)
    check("every mobile map control is inside the viewport and pointer-accessible", js("Array.from(document.querySelectorAll('.citymap-controls button')).every(button => { const r=button.getBoundingClientRect(); const at=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2); return r.width>=44 && r.height>=44 && r.x>=0 && r.right<=innerWidth && r.y>=0 && r.bottom<=innerHeight && (at===button||button.contains(at)); })"))
    attribution = attribution_state()
    EVIDENCE["mobile_attribution"] = attribution
    check("mobile attribution links remain visible and pointer-accessible above the cards", attribution["clear"] and bool(attribution["links"]) and all(link["accessible"] for link in attribution["links"]), attribution)
    clearance = marker_clearance()
    EVIDENCE["mobile_marker_clearance"] = clearance
    check("mobile selected-place label clears the map controls", not clearance["overlap"], clearance)
    ab("screenshot", str(shots / "mobile-3d.png"))
    ab("click", mode_button("2D"))
    wait_camera()
    flat = js(STATE)
    check("mobile 2D pointer action hides depth and locks the camera flat", flat["pitch"] == 0 and flat["maxPitch"] == 0 and all(layer["visibility"] == "none" for layer in flat["depthLayers"]) and one_canvas())
    ab("screenshot", str(shots / "mobile-2d.png"))
    ab("click", mode_button("3D"))
    wait_camera()
    check("mobile returns to embedded 3D with the same source route", one_canvas() and js(STATE)["pitch"] >= 30 and exact_route())
    ab("click", '[aria-label="Assistant"]')
    check("mobile assistant opens while preserving the map instance", js("getComputedStyle(document.querySelector('.assistant-pane')).display === 'flex'") and one_canvas())
    ab("click", '[aria-label="Explore map"]')
    wait_camera()
    check("returning from mobile assistant resizes the same canvas", js("getComputedStyle(document.querySelector('.map-stage')).visibility === 'visible'") and one_canvas())
    EVIDENCE["mobile_final"] = js(STATE)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screens-dir", default="/tmp/qala-embedded-map-review")
    parser.add_argument("--publish-screens", action="store_true", help="Copy the four verified screenshots into artifacts/screenshots/v4-embedded-*.png")
    args = parser.parse_args()
    shots = Path(args.screens_dir)
    shots.mkdir(parents=True, exist_ok=True)
    failure = None
    try:
        desktop(shots)
        mobile(shots)
        errors = ab("errors").strip()
        check("no uncaught browser exceptions", not errors, errors or None)
    except Exception as error:
        failure = str(error)
        print("Verification stopped: " + failure, flush=True)
    finally:
        screenshots = [str(path) for path in sorted(shots.glob("*.png"))]
        if args.publish_screens:
            screenshots = []
            for path in sorted(shots.glob("*.png")):
                destination = ROOT / "artifacts/screenshots" / ("v4-embedded-" + path.name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
                screenshots.append(str(destination.relative_to(ROOT)))
        report = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "base_url": BASE_URL,
            "method": "agent-browser 0.27.0; actual production frontend, real FastAPI, OpenFreeMap vector tiles and Valhalla street geometry; pointer actions except explicitly scripted rapid-toggle stress; no mocked API responses",
            "injected_boundaries": ["Synthetic geolocation callbacks after explicit live-location activation; no physical GPS measured", "Camera bearing/center displaced using the real MapLibre API to test visible reset controls", "12 programmatic toggles at 25 ms intervals to exercise interrupted transitions"],
            "coverage_limits": ["Extrusions depict OSM building footprints and available heights, not verified architectural landmark meshes", "Headless software-rendering checks do not establish physical-device FPS or a completed outdoor walk"],
            "checks": CHECKS, "passed": sum(row["passed"] for row in CHECKS), "total": len(CHECKS),
            "failure": failure, "evidence": EVIDENCE,
            "screenshots": screenshots,
        }
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        ab("close")
    print(f"{report['passed']}/{report['total']} embedded-map browser checks passed", flush=True)
    if failure or report["passed"] != report["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
