#!/usr/bin/env python3
"""Real-map catalogue proof. Uses agent-browser and actual public map/API data.

Camera positioning is scripted to reach city/venue scales. Cluster, venue and
keyboard controls use actual pointer/keyboard input. No provider is mocked.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path

os.environ.setdefault("QALA_BROWSER_SESSION", "qala-map-catalog")
from capture_demo import ab, js, ROOT, BASE_URL, CMD
from verify_embedded_map import MAP

CMD[:] = [os.getenv("QALA_AGENT_BROWSER_BIN", "/home/lain/.npm/_npx/6de2aa2fded2970c/node_modules/agent-browser/bin/agent-browser-linux-x64"), "--session", os.environ["QALA_BROWSER_SESSION"]]
CHECKS = []
SHOTS = ROOT / "artifacts/screenshots/map-catalog"


def check(name, condition):
    CHECKS.append({"check": name, "passed": bool(condition)})
    print(("PASS " if condition else "FAIL ") + name, flush=True)
    assert condition, name


def wait(expression):
    # Return a boolean, never a DOM node carrying React/MapLibre object graphs.
    ab("wait", "--fn", "Boolean(" + expression + ")")


def click_point(point):
    ab("mouse", "move", str(round(point["x"])), str(round(point["y"])))
    ab("mouse", "down")
    ab("mouse", "up")


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    failure = None
    evidence = {}
    try:
        ab("set", "viewport", "1440", "1000")
        ab("open", BASE_URL)
        wait("Boolean(" + MAP + ") && !document.querySelector('.citymap-loading')")
        js("window.__catalogMap=" + MAP + ";window.__catalogCanvas=window.__catalogMap.getCanvas();true")
        wait("window.__catalogMap.getSource('qala-catalog') && window.__catalogMap.isSourceLoaded('qala-catalog') && !window.__catalogMap.isMoving()")
        wait("(window.__catalogMap.getSource('qala-catalog')?.serialize().data?.geojson ?? window.__catalogMap.getSource('qala-catalog')?.serialize().data)?.features?.length>6500")
        wait("document.querySelector('.place-card') && !document.querySelector('.route-loading') && !document.querySelector('.map-status[role=status]')")
        evidence["bundle"] = js("document.querySelector('script[src*=\"/assets/index-\"]')?.getAttribute('src')")
        coverage = js("(async()=>{const map=window.__catalogMap,data=await map.getSource('qala-catalog').getData(),expected=await fetch('/api/pois/map').then(r=>r.json());const ids=data.features.map(f=>f.properties.id),actual=[...ids].sort(),wanted=expected.features.map(f=>f.properties.id).sort();return{count:ids.length,unique:new Set(ids).size,exact:JSON.stringify(actual)===JSON.stringify(wanted),options:map.getSource('qala-catalog').getClusterOptions(),domMarkers:document.querySelectorAll('.citymap-place-marker').length};})()")
        evidence["coverage"] = coverage
        check("every visible source POI is loaded into the map exactly once", coverage["exact"] and coverage["count"] == coverage["unique"] and coverage["count"] > 6500)
        check("GPU clusters replace thousands of DOM markers", coverage["options"]["cluster"] and coverage["domMarkers"] <= 3)
        check("initial catalogue load does not request paid source profiles", js("!performance.getEntriesByType('resource').some(r=>r.name.includes('/sources/2gis'))"))
        js("window.__catalogRoute=JSON.stringify(window.__catalogMap.getSource('qala-route').serialize().data);window.__catalogMap.jumpTo({center:[71.43,51.13],zoom:12,padding:{top:0,bottom:0,left:0,right:0}});true")
        wait("window.__catalogMap.loaded() && !window.__catalogMap.isMoving()")
        point = js("(()=>{const m=window.__catalogMap,r=m.getCanvas().getBoundingClientRect();for(const f of m.queryRenderedFeatures(undefined,{layers:['qala-catalog-clusters']})){const p=m.project(f.geometry.coordinates);if(p.x>60&&p.x<r.width-100&&p.y>210&&p.y<r.height-280)return{x:p.x+r.x,y:p.y+r.y,zoom:m.getZoom()};}return null;})()")
        check("city view renders selectable inventory clusters", bool(point))
        click_point(point)
        wait("!window.__catalogMap.isMoving()")
        check("actual cluster click expands the same map", js("window.__catalogMap.getZoom()") > point["zoom"])
        js("(async()=>{const d=await window.__catalogMap.getSource('qala-catalog').getData();window.__catalogTarget=d.features.find(f=>f.properties.id==='osm-way-454857501');window.__catalogMap.jumpTo({center:window.__catalogTarget.geometry.coordinates,zoom:18,padding:{top:0,bottom:0,left:0,right:0}});return true;})()")
        wait("window.__catalogMap.loaded() && !window.__catalogMap.isMoving()")
        point = js("(()=>{const m=window.__catalogMap,p=m.project(window.__catalogTarget.geometry.coordinates),r=m.getCanvas().getBoundingClientRect();return{x:p.x+r.x,y:p.y+r.y};})()")
        click_point(point)
        wait("document.querySelector('.evidence-dialog .place-details')")
        check("actual catalogue point opens the source-backed venue details", js("document.querySelector('.evidence-dialog [data-slot=dialog-title]')?.textContent.includes('Alem.ai')"))
        check("catalogue details never invent route or visit durations", js("!document.querySelector('.evidence-dialog .place-detail-times')"))
        ab("press", "Escape")
        check("venue browsing preserves active route and map canvas", js("window.__catalogCanvas===window.__catalogMap.getCanvas()&&window.__catalogRoute===JSON.stringify(window.__catalogMap.getSource('qala-route').serialize().data)"))
        ab("click", '[aria-label="Switch to 2D map"]')
        check("2D hides all depth and locks pitch while retaining catalogue", js("window.__catalogMap.getPitch()===0&&window.__catalogMap.getMaxPitch()===0&&window.__catalogMap.getStyle().layers.filter(l=>l.type==='fill-extrusion').every(l=>window.__catalogMap.getLayoutProperty(l.id,'visibility')==='none')&&!!window.__catalogMap.getLayer('qala-catalog-points')"))
        ab("click", '[aria-label="Switch to 3D map"]')
        wait("!window.__catalogMap.isMoving()")
        check("3D restores inside the existing canvas and route", js("window.__catalogMap.getPitch()>30&&window.__catalogCanvas===window.__catalogMap.getCanvas()&&window.__catalogRoute===JSON.stringify(window.__catalogMap.getSource('qala-route').serialize().data)"))
        js("window.__catalogMap.jumpTo({center:[71.43,51.13],zoom:14,padding:{top:0,bottom:0,left:0,right:0}});true")
        wait("!window.__catalogMap.isMoving() && window.__catalogMap.loaded()")
        ab("screenshot", str(SHOTS / "desktop-map.png"))
        js("document.querySelector('[aria-label=\"Places on the map\"]').focus();true")
        ab("press", "Enter")
        wait("document.querySelector('.catalog-browser')")
        check("keyboard opens a focus-managed equivalent place browser", js("document.querySelector('.catalog-browser').contains(document.activeElement)"))
        ab("fill", '.catalog-browser input', "Alem.ai")
        check("native browse search exposes source venue", js("document.querySelector('.catalog-browser-results li strong')?.textContent.includes('Alem.ai')"))
        ab("click", '.catalog-browser-results li button')
        wait("document.querySelector('.evidence-dialog .place-details')")
        ab("press", "Escape")
        ab("set", "viewport", "390", "844")
        ab("wait", "500")
        ab("screenshot", str(SHOTS / "mobile-map.png"))
        check("mobile catalogue button is visible and unobstructed", js("(()=>{const b=document.querySelector('[aria-label=\"Places on the map\"]'),r=b.getBoundingClientRect(),hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return r.width>=44&&r.height>=44&&(hit===b||b.contains(hit));})()"))
        ab("click", '[aria-label="Places on the map"]')
        wait("document.querySelector('.catalog-browser')")
        ab("fill", '.catalog-browser input', "")
        wait("document.querySelectorAll('.catalog-browser-results li').length===40")
        check("mobile catalogue renders a full first page of source places", js("document.querySelectorAll('.catalog-browser-results li').length===40"))
        check("mobile browse has usable touch targets and no page overflow", js("document.documentElement.scrollWidth<=innerWidth&&[...document.querySelectorAll('.catalog-browser-results li button')].every(e=>e.getBoundingClientRect().height>=44)"))
        ab("screenshot", str(SHOTS / "mobile-browser.png"))
        ab("press", "Escape")
        ab("screenshot", str(SHOTS / "mobile-map.png"))
    except Exception as error:
        failure = str(error)
        raise
    finally:
        if failure:
            ab("screenshot", str(SHOTS / "failure-state.png"))
        report = {"recorded_at": datetime.now(timezone.utc).isoformat(), "base_url": BASE_URL,
                  "method": "agent-browser, real production API and MapLibre6/OpenFreeMap; no mocked data. Scripted camera positioning; real pointer cluster/point selection and keyboard actions.",
                  "checks": CHECKS, "passed": sum(c["passed"] for c in CHECKS), "total": len(CHECKS),
                  "failure": failure, "evidence": evidence,
                  "screenshots": [str(p.relative_to(ROOT)) for p in sorted(SHOTS.glob("*.png"))]}
        (ROOT / "artifacts/map-catalog-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        ab("close")


if __name__ == "__main__":
    main()
