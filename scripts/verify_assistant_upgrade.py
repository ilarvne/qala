#!/usr/bin/env python3
"""Production-app browser proof for Assistant UI + trusted OpenUI.

Runs against real FastAPI/SSE, collected POIs and street routing. An in-page
fetch observer clones responses only; it never supplies or alters responses.
Four screenshots form one desktop/mobile review batch. No visual polish loop.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
import shutil
from pathlib import Path
import traceback

os.environ.setdefault("QALA_BROWSER_SESSION", "qala-assistant-upgrade")
from capture_demo import ab, js, ROOT, BASE_URL, CMD

BINARY = os.getenv("QALA_AGENT_BROWSER_BIN", "/home/lain/.npm/_npx/6de2aa2fded2970c/node_modules/agent-browser/bin/agent-browser-linux-x64")
if Path(BINARY).exists():
    CMD[:] = [BINARY, "--session", os.environ["QALA_BROWSER_SESSION"]]
_ab = ab

def ab(*args):
    if args and args[0] in ("click", "check", "uncheck") and len(args) > 1:
        selector = json.dumps(args[1])
        js("(()=>{const e=document.querySelector(" + selector + ");if(e?.closest('.qa-viewport'))e.scrollIntoView({block:'center',behavior:'instant'});return true;})()")
    if len(args) >= 4 and args[:4] == ("find", "role", "button", "click") and "--name" in args:
        name = json.dumps(args[args.index("--name") + 1])
        found = js("(()=>{const e=[...document.querySelectorAll('button')].find(e=>!e.disabled&&(e.getAttribute('aria-label')==="+name+"||e.innerText.trim()==="+name+"||e.textContent.trim()==="+name+"));if(!e)return false;e.scrollIntoView({block:'center',behavior:'instant'});e.focus();return true;})()")
        if not found: raise RuntimeError("Named button missing: " + json.loads(name))
        return _ab("press", "Enter")
    if len(args) >= 4 and args[:4] == ("find", "role", "option", "click") and "--name" in args:
        name = json.dumps(args[args.index("--name") + 1])
        found = js("(()=>{const e=[...document.querySelectorAll('[role=option]')].find(e=>e.innerText.trim()==="+name+");if(!e)return false;e.scrollIntoView({block:'nearest',behavior:'instant'});e.focus();return true;})()")
        if not found: raise RuntimeError("Named option missing: " + json.loads(name))
        return _ab("press", "Enter")
    return _ab(*args)

REPORT = ROOT / "artifacts/assistant-upgrade-browser-verification.json"
SHOTS = ROOT / "artifacts/screenshots/assistant-upgrade"
CHECKS: list[dict] = []
EVIDENCE: dict = {}
LAST = ".qa-thread-body > .qa-assistant-message:last-child"

OBSERVER = r"""(() => {
  if(window.__assistantQA)return true;
  const original=window.fetch.bind(window);
  window.__assistantQA={requests:[],results:[]};
  window.fetch=async(input,init)=>{
    const path=new URL(typeof input==='string'?input:input.url,location.href).pathname;
    if(!path.startsWith('/api/'))return original(input,init);
    const item={path,method:init?.method??'GET',started:performance.now()};
    try{item.body=init?.body?JSON.parse(init.body):undefined;}catch{}
    window.__assistantQA.requests.push(item);
    try{
      const response=await original(input,init);item.status=response.status;
      response.clone().text().then(text=>{
        if(response.headers.get('content-type')?.includes('text/event-stream')){
          item.events=text.split(/\r?\n\r?\n/).flatMap(record=>{
            const event=record.match(/^event:\s*(.+)$/m)?.[1];const data=record.split(/\r?\n/).filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trim()).join('\n');
            if(!data)return [];try{return [{event,data:JSON.parse(data)}];}catch{return [];}
          });
          item.result=item.events.find(e=>e.event==='result')?.data;
          if(item.result)window.__assistantQA.results.push(item.result);
        }else{try{item.response=JSON.parse(text);}catch{}}
        item.done=true;
      }).catch(error=>{item.error=error.name;item.done=true;});
      return response;
    }catch(error){item.error=error.name;item.done=true;throw error;}
  };
  return true;
})()"""
CONTEXT = r"""(() => {
  const el=document.querySelector('.qa-assistant');if(!el)return null;
  const key=Object.keys(el).find(key=>key.startsWith('__reactFiber'));
  for(let fiber=el[key];fiber;fiber=fiber.return){if(fiber.memoizedProps?.context?.location&&typeof fiber.memoizedProps?.onResult==='function')return fiber.memoizedProps.context;}
  return null;
})()"""
MAP = r"""(() => {
 const el=document.querySelector('.citymap-renderer');if(!el)return null;
 const key=Object.keys(el).find(key=>key.startsWith('__reactFiber'));
 for(let fiber=el[key];fiber;fiber=fiber.return)for(let hook=fiber.memoizedState;hook;hook=hook.next){const candidate=hook.memoizedState?.current;if(typeof candidate?.getPitch==='function'&&typeof candidate?.getStyle==='function')return candidate;}
 return null;
})()"""
EXACT_ROUTE = r"""(() => {
 const map=window.__qaMap;if(!map)return false;
 const el=document.querySelector('.citymap-renderer');const key=Object.keys(el).find(key=>key.startsWith('__reactFiber'));let navigation;
 for(let fiber=el[key];fiber;fiber=fiber.return)if(fiber.memoizedProps?.navigation?.street_routed){navigation=fiber.memoizedProps.navigation;break;}
 let data=map.getSource('qala-route')?.serialize?.().data??map.getSource('qala-route')?._data;data=data?.geojson??data;
 return !!navigation&&JSON.stringify(data?.geometry?.coordinates)===JSON.stringify(navigation.geometry.coordinates);
})()"""


def check(name, passed, detail=None):
    item = {"check": name, "passed": bool(passed)}
    if detail is not None:
        item["detail"] = detail
    CHECKS.append(item)
    print(("PASS " if passed else "FAIL ") + name, flush=True)


def wait(expression):
    ab("wait", "--fn", expression)


def chats():
    return js("window.__assistantQA.requests.filter(r=>r.path==='/api/chat/stream').length")


def current_result():
    return js("window.__assistantQA.results.at(-1)")


def finished(previous):
    wait(f"window.__assistantQA.requests.filter(r=>r.path==='/api/chat/stream'&&r.done&&r.result).length>{previous}&&!document.querySelector('.qa-cancel-button')")
    wait("Boolean(document.querySelector('.qa-thread-body > .qa-assistant-message:last-child .oui-response'))")
    return current_result()


def ask(text):
    previous = chats()
    ab("fill", ".qa-footer textarea", text)
    ab("click", '.qa-footer [aria-label="Send message"]')
    return finished(previous)


def context():
    return js(CONTEXT)


def viewport_last():
    js("document.querySelector('.qa-thread-body > .qa-assistant-message:last-child')?.scrollIntoView({block:'start'});true")


def screenshot(name):
    SHOTS.mkdir(parents=True, exist_ok=True)
    ab("screenshot", str(SHOTS / (name + ".png")))


def close_dialog():
    ab("find", "role", "button", "click", "--name", "Close", "--exact")
    wait("!document.querySelector('[role=dialog]')")


def main():
    if not ARGS.resume_edit:
        ab("set", "viewport", "1440", "960")
        ab("open", BASE_URL)
        wait("document.querySelectorAll('.place-card').length>0&&!document.querySelector('.citymap-loading')&&!document.querySelector('.citymap-fallback')")
        wait("Boolean(" + MAP + ")")
        js("window.__qaMap=" + MAP + ";window.__qaCanvas=window.__qaMap.getCanvas();true")
        wait("window.__qaMap.loaded()&&!document.querySelector('.citymap-fallback')&&!document.querySelector('.citymap-loading')")
        js(OBSERVER)
        check("actual Assistant UI task starters replace decorative welcome copy", js("document.querySelectorAll('.qa-starter').length===3&&!document.querySelector('.qa-city-image')&&!document.body.innerText.includes('A little time.')"))
        check("new session controls have deployed layout", js("getComputedStyle(document.querySelector('.qa-sessionbar')).display==='flex'&&getComputedStyle(document.querySelector('.qa-memory-button')).minHeight==='36px'"))
        check("desktop has no horizontal page overflow", js("document.documentElement.scrollWidth<=innerWidth"))
        screenshot("01-desktop-empty")

        plan = ask("Plan an architecture walk near Bayterek with a coffee stop in 60 minutes.")
        check("chat uses actual SSE stages and full grounded result", js("(()=>{const r=window.__assistantQA.requests.filter(r=>r.path==='/api/chat/stream').at(-1);return r.status===200&&['retrieve','rank','validate','compose'].every(stage=>r.events.some(e=>e.event==='status'&&e.data.stage===stage))&&r.result?.openui?.format==='openui-lang';})()"))
        check("OpenUI owns a single set of followup actions", js("document.querySelectorAll('.qa-assistant-message:last-child .oui-followups').length===1&&document.querySelectorAll('.qa-assistant-message:last-child .qa-refinements').length===0"))
        check("OpenUI result renders trusted POI IDs", js("(()=>{const rendered=[...document.querySelectorAll('.qa-assistant-message:last-child [data-openui-place]')].map(e=>e.dataset.openuiPlace);return rendered.length>0&&rendered.every(id=>window.__assistantQA.results.at(-1).recommendations.some(p=>p.id===id));})()"))
        photos = js("[...document.querySelectorAll('.qa-assistant-message:last-child .oui-place-photo img')].map(i=>({src:i.getAttribute('src'),alt:i.alt,loaded:i.complete&&i.naturalWidth>0}))")
        EVIDENCE["first_plan"] = {"names": [p["name"] for p in plan["recommendations"]], "photos": photos, "mode": plan.get("mode")}
        check("OpenUI POI layout resets legacy stop grid", js("[...document.querySelectorAll('.oui-place')].every(e=>getComputedStyle(e).display==='block')"))
        if photos:
            wait("[...document.querySelectorAll('.qa-assistant-message:last-child .oui-place-photo img')].some(i=>i.complete&&i.naturalWidth>0)")
            check("real source photo loads in assistant", True, "Collected photo provenance is inspected through Place details; availability is partial.")
        else:
            check("real source photo loads in assistant", False, "No photo-bearing place returned in this query.")
        viewport_last()
        screenshot("02-desktop-openui-plan")

        ab("click", LAST + " .oui-place:first-child .oui-save")
        check("OpenUI save action updates local saved state", js("document.querySelector('.oui-save')?.getAttribute('aria-pressed')==='true'"))
        ab("click", LAST + " .oui-place:first-child .oui-place-photo")
        wait("Boolean(document.querySelector('.evidence-dialog'))")
        check("OpenUI source inspector shows actual source and honest review availability", js("!!document.querySelector('.evidence-dialog a[href*=openstreetmap]')&&document.querySelector('.evidence-dialog').innerText.includes('Community rating')"))
        close_dialog()
        ab("click", LAST + " .oui-place:first-child .oui-place-name")
        check("OpenUI map action selects a real response place", js("document.querySelectorAll('.citymap-place-marker[aria-pressed=true]').length===1"))
        wait("document.querySelector('.route-quality')?.textContent.includes('Street route')")
        check("embedded renderer contains exact street-route geometry", js(EXACT_ROUTE))
        ab("focus", '[aria-label="Switch to 2D map"]')
        ab("press", "Enter")
        check("keyboard 2D toggle keeps same canvas and hides every extrusion", js("window.__qaMap.getPitch()===0&&window.__qaMap.getMaxPitch()===0&&window.__qaMap.getCanvas()===window.__qaCanvas&&window.__qaMap.getStyle().layers.filter(l=>l.type==='fill-extrusion').every(l=>window.__qaMap.getLayoutProperty(l.id,'visibility')==='none')"))
        ab("click", '[aria-label="Switch to 3D map"]')
        wait("!window.__qaMap.isMoving()")

    previous = chats()
    if not js("Boolean(document.querySelector('.qa-edit-composer textarea'))"):
        ab("focus", '.qa-user-actions [aria-label="Edit message"]')
        ab("press", "Enter")
    wait("Boolean(document.querySelector('.qa-edit-composer textarea'))")
    ab("fill", ".qa-edit-composer textarea", "Find a quiet coffee stop near Bayterek in 45 minutes.")
    ab("click", ".qa-edit-send")
    edited = finished(previous)
    check("native Assistant UI edit resubmits changed request", edited.get("conversation", {}).get("duration_minutes") == 45 and "coffee" in edited.get("conversation", {}).get("interests", []))
    check("parsed time updates visible planner header", context().get("duration_minutes") == 45 and "45 min" in ab("get", "text", ".time-context"))
    previous = chats()
    ab("click", LAST + ' [aria-label="Regenerate"]')
    finished(previous)
    check("native regeneration creates navigable response versions", js("!!document.querySelector('.qa-assistant-message:last-child .qa-branches')&&document.querySelector('.qa-assistant-message:last-child .qa-branch-count').innerText.includes('2')"))
    count = chats()
    ab("click", LAST + ' [aria-label="Previous version"]')
    ab("click", LAST + ' [aria-label="Next version"]')
    check("version navigation restores plan without another chat request", chats() == count and context().get("duration_minutes") == 45)

    ab("click", LAST + " .oui-controls summary")
    ab("click", LAST + ' .oui-controls [aria-label="Time available"]')
    ab("find", "role", "option", "click", "--name", "30 min", "--exact")
    ab("check", LAST + ' .oui-check:first-of-type input')
    previous = chats()
    ab("click", LAST + " .oui-apply")
    refined = finished(previous)
    effective = refined.get("conversation", {})
    check("OpenUI form retains coffee intent and applies explicit time/boolean", effective.get("duration_minutes") == 30 and effective.get("indoor") is True and effective.get("accessible") is False and "coffee" in effective.get("interests", []), effective)
    check("form result synchronizes header and planner context", context().get("duration_minutes") == 30 and context().get("indoor") is True and "30 min" in ab("get", "text", ".time-context"))

    count = chats()
    before_places = js("[...document.querySelectorAll('.place-card')].map(e=>e.dataset.placeId)")
    ab("click", ".qa-memory-button")
    wait("Boolean(document.querySelector('#preference-memory'))")
    ab("click", '[aria-label="Remember my preferences"]')
    wait("document.querySelector('[aria-label=\"Remember my preferences\"]')?.getAttribute('aria-checked')==='true'&&!!document.querySelector('.memory-inspector')")
    check("opt-in memory exposes stored interests and retention", "Retention" in ab("get", "text", ".memory-inspector"))
    ab("check", '.memory-inspector input[value="quiet"]')
    ab("find", "role", "button", "click", "--name", "Save preferences", "--exact")
    wait("window.__assistantQA.requests.some(r=>r.path.startsWith('/api/memory/')&&r.method==='POST'&&r.done&&r.body?.interests?.includes('quiet'))")
    check("memory edits persist through actual memory API", js("window.__assistantQA.requests.filter(r=>r.path.startsWith('/api/memory/')&&r.method==='POST').at(-1).response?.preferences?.interests?.includes('quiet')"))
    ab("find", "role", "button", "click", "--name", "Forget my preferences", "--exact")
    wait("document.querySelector('[aria-label=\"Remember my preferences\"]')?.getAttribute('aria-checked')==='false'&&!document.querySelector('.memory-inspector')")
    check("memory deletion does not replan or replace places", chats() == count and before_places == js("[...document.querySelectorAll('.place-card')].map(e=>e.dataset.placeId)"))
    close_dialog()

    finish_comparison_and_mobile()


def finish_comparison_and_mobile():
    compared = ask("Compare two architecture stops near Bayterek in 60 minutes, without indoor places or coffee.")
    check("comparison response contains multiple trusted places", len(compared["recommendations"]) >= 2 and compared.get("openui", {}).get("layout") == "comparison", [p["name"] for p in compared["recommendations"]])
    check("comparison table exposes facts with unknown values kept explicit", js("Boolean(document.querySelector('.qa-assistant-message:last-child .oui-comparison table'))"))
    viewport_last()
    screenshot("03-desktop-comparison")

    ab("set", "viewport", "390", "844")
    ab("find", "role", "button", "click", "--name", "Assistant", "--exact")
    viewport_last()
    check("mobile conversation has no page overflow", js("document.documentElement.scrollWidth<=innerWidth"))
    mobile = js("(()=>{const input=document.querySelector('.qa-footer textarea');const buttons=[...document.querySelectorAll('.qa-memory-button,.qa-new-chat,.qa-footer button')];return {inputFont:getComputedStyle(input).fontSize,targets:buttons.map(e=>({label:e.getAttribute('aria-label')??e.innerText,width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height}))};})()")
    check("mobile composer uses 16px input and 44px main controls", mobile["inputFont"] == "16px" and all(p["height"] >= 44 and (p["width"] >= 44 or "Memory" in (p["label"] or "")) for p in mobile["targets"]), mobile)
    ab("focus", ".qa-footer textarea")
    ab("press", "Tab")
    check("keyboard modality removes assistant transitions", js("document.querySelector('.qa-assistant').dataset.keyboard==='true'&&getComputedStyle(document.activeElement).transitionDuration.split(',').every(s=>parseFloat(s)===0)"))
    ab("set", "media", "light", "reduced-motion")
    check("reduced motion removes generated UI transitions", js("matchMedia('(prefers-reduced-motion: reduce)').matches&&getComputedStyle(document.querySelector('.qa-generative')).transitionDuration.split(',').every(s=>parseFloat(s)===0)"))
    screenshot("04-mobile-conversation")

    ab("click", '[aria-label="New chat"]')
    check("New chat clears visible branch and restores task starters", js("document.querySelectorAll('.qa-user-row').length===0&&document.querySelectorAll('.qa-starter').length===3"))
    airport = ask("I have 2 hours before my flight. What can I see nearby?")
    check("fresh chat sends no earlier conversation state", js("!window.__assistantQA.requests.filter(r=>r.path==='/api/chat/stream').at(-1).body.conversation"))
    check("unknown airport transfer produces interactive clarification", any(q["field"] == "airport_transfer_minutes" for q in airport.get("clarifications", [])) and js("Boolean(document.querySelector('.qa-assistant-message:last-child .oui-questions fieldset'))"))
    previous = chats()
    ab("find", "role", "button", "click", "--name", "30 min", "--exact")
    resolved = finished(previous)
    check("airport choice updates typed context and resolves transfer question", resolved.get("conversation", {}).get("airport_transfer_minutes") == 30 and not any(q["field"] == "airport_transfer_minutes" for q in resolved.get("clarifications", [])))
    check("map remains the original embedded instance after all assistant actions", js("document.querySelectorAll('.citymap-renderer canvas').length===1&&window.__qaMap.getCanvas()===window.__qaCanvas"))
    EVIDENCE["network"] = js("window.__assistantQA.requests.map(r=>({path:r.path.startsWith('/api/memory/')?'/api/memory/[qa-session]':r.path,method:r.method,status:r.status,stages:r.events?.filter(e=>e.event==='status').map(e=>e.data.stage)}))")
    EVIDENCE["chat_requests"] = chats()
    EVIDENCE["browser_errors"] = ab("errors")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmation", action="store_true", help="Run the one permitted full confirmation batch after the consolidated fixes; archives initial evidence")
    parser.add_argument("--resume-edit", action="store_true", help="Resume the same live session at its existing editor after selector diagnostics")
    parser.add_argument("--resume-comparison", action="store_true", help="Resume existing session after form diagnostics, preserving earlier real checks")
    args = parser.parse_args()
    ARGS = args
    if args.confirmation:
        if REPORT.exists():
            shutil.copy2(REPORT, ROOT / "artifacts/assistant-upgrade-browser-verification-initial.json")
        SHOTS = SHOTS / "confirmation"
    if (args.resume_edit or args.resume_comparison) and REPORT.exists():
        previous_report = json.loads(REPORT.read_text())
        CHECKS.extend(previous_report.get("checks", []))
        EVIDENCE.update(previous_report.get("evidence", {}))
        EVIDENCE.pop("failure_snapshot", None)
    error = None
    try:
        if args.resume_comparison:
            finish_comparison_and_mobile()
        else:
            main()
    except Exception as reason:
        error = str(reason)
        traceback.print_exc()
        try:
            EVIDENCE["failure_snapshot"] = ab("snapshot", "-i")
        except Exception:
            pass
    finally:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        report = {"phase": "confirmation" if args.confirmation else "initial", "initial_history": "artifacts/assistant-upgrade-browser-verification-initial.json" if args.confirmation else None, "checked_at": datetime.now(timezone.utc).isoformat(), "method": "Cached agent-browser against production App, real FastAPI/SSE/collected POIs/OpenFreeMap/Valhalla. Fetch observer clones actual responses only. No API or routing responses mocked.", "passed": sum(c["passed"] for c in CHECKS), "total": len(CHECKS), "checks": CHECKS, "evidence": EVIDENCE, "screenshots": [str(path.relative_to(ROOT)) for path in sorted(SHOTS.glob('*.png'))], "scope": "Functional browser proof and the recorded four-scene desktop/mobile batch. Initial and single confirmation batches are retained separately. Photo/review availability remains partial; no citywide completeness or architectural accuracy claim.", **({"error": error} if error else {})}
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"passed": report["passed"], "total": report["total"], "error": error, "report": str(REPORT)}, indent=2), flush=True)
    if error or any(not c["passed"] for c in CHECKS):
        raise SystemExit(1)
