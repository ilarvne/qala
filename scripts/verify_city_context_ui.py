#!/usr/bin/env python3
"""Actual browser proof for sourced events, weather and integration disclosures."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

os.environ["QALA_BROWSER_SESSION"] = "qala-context-upgrade"
from capture_demo import ab, js, ROOT, CMD

CMD[:] = ["/home/lain/.npm/_npx/6de2aa2fded2970c/node_modules/agent-browser/bin/agent-browser-linux-x64", "--session", "qala-context-upgrade"]
OUT = ROOT / "artifacts/screenshots/city-context"
checks, evidence = [], {}


def check(name, passed):
    checks.append({"name": name, "passed": bool(passed)})
    if not passed:
        raise AssertionError(name)


def wait(expression):
    ab("wait", "--fn", expression)


def open_integration(name):
    index = js("[...document.querySelectorAll('.integration-list > details')].findIndex(e=>e.querySelector('summary > span')?.textContent===" + json.dumps(name) + ")")
    if not isinstance(index, int) or index < 0:
        raise AssertionError("Provider disclosure not found: " + name)
    selector = f".integration-list > details:nth-child({index + 1}) summary"
    ab("scrollintoview", selector)
    ab("click", selector)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ab("set", "viewport", "1600", "1000")
    ab("open", "http://localhost:8000/")
    wait("document.querySelectorAll('.place-card').length > 0")
    js(r"""(() => {
      window.__cityResults=[]; const original=window.fetch.bind(window);
      window.fetch=async(...args)=>{const response=await original(...args);
        if(['/api/recommend','/api/chat/stream'].some(path=>String(args[0]).includes(path))) response.clone().text().then(text=>{
          try{if(response.headers.get('content-type')?.includes('event-stream')){
            for(const part of text.split(/\r?\n\r?\n/)) if(/^event:\s*result$/m.test(part))
              window.__cityResults.push(JSON.parse(part.split('\n').filter(x=>x.startsWith('data:')).map(x=>x.slice(5).trim()).join('\n')));
          }else window.__cityResults.push(JSON.parse(text));}catch{}
        });return response;};return true;
    })()""")
    ab("click", '[aria-label="Language"]')
    ab("find", "role", "option", "click", "--name", "RU", "--exact")
    wait("document.querySelector('[data-testid=scenario-events]')?.textContent.includes('Афиша')")
    ab("click", "[data-testid=scenario-events]")
    wait("window.__cityResults.at(-1)?.context.event_only_request===true && document.querySelector('.event-map-state .official-events a')!==null")
    event = js("(()=>{const r=window.__cityResults.at(-1);return {events:r.events,poi_count:r.recommendations.length,coordinates:r.route.coordinates,weather:r.context.weather};})()")
    evidence["events"] = event
    check("official event data rendered as source links", bool(event["events"]) and all(x["url"].startswith("https://a-vm.kz/events/") for x in event["events"]))
    check("events do not manufacture map stops or route", event["poi_count"] == 0 and event["coordinates"] == [])
    check("event state avoids unrelated empty-place prompt", js("!document.querySelector('.empty-map-state')"))
    check("event response avoids estimated-walking disclaimer", js("![...document.querySelectorAll('.qa-assistant-message:last-child .oui-evidence p')].some(e=>e.textContent.includes('Время пешком'))"))
    ab("screenshot", str(OUT / "desktop-events.png"))
    ab("fill", ".qa-composer-input", "Хочу кофе рядом, только в помещении, не на улице")
    ab("press", "Enter")
    wait("window.__cityResults.at(-1)?.recommendations.length>0 && window.__cityResults.at(-1)?.conversation.indoor===true")
    wait("document.querySelector('.qa-assistant-message:last-child .oui-evidence summary')!==null")
    ab("click", ".qa-assistant-message:last-child .oui-evidence summary")
    walking = js("(()=>{const r=window.__cityResults.at(-1);return {weather:r.context.weather,effect:r.context.weather_effect,indoor:r.conversation.indoor,categories:r.recommendations.map(p=>p.category),events:r.events||[]};})()")
    evidence["walking"] = walking
    check("explicit indoor negation survives real chat", walking["indoor"] is True and walking["effect"]["explicit_outdoor_request"] is False)
    check("coffee exits calendar context", all(x == "cafe" for x in walking["categories"]) and not walking["events"])
    check("actual forecast rendered inside source disclosure", walking["weather"]["status"] == "available" and js("document.querySelector('.qa-assistant-message:last-child .context-source')?.textContent.includes('Open-Meteo')"))
    check("forecast period and retrieval time disclosed", js("document.querySelector('.qa-assistant-message:last-child .context-source')?.textContent.includes('Интервал прогноза') && document.querySelector('.qa-assistant-message:last-child .context-source')?.textContent.includes('Получен')"))
    ab("scrollintoview", ".qa-assistant-message:last-child .context-source")
    ab("screenshot", str(OUT / "desktop-weather.png"))
    ab("find", "role", "button", "click", "--name", "Настройки и приватность", "--exact")
    wait("document.querySelectorAll('.integration').length > 10")
    integration_data = js("fetch('/api/integrations').then(r=>r.json()).then(d=>d.integrations)")
    evidence["integrations"] = integration_data
    check("imported Overture provenance visible", any(x["id"] == "overture" for x in integration_data))
    check("Google restrictions do not trigger provider-key map replacement", any(x["id"] == "google_places" and x["status"] == "restricted" for x in integration_data))
    open_integration("Open-Meteo")
    check("provider verification has explicit accessible text", js("[...document.querySelectorAll('.integration[open]')].some(e=>e.textContent.includes('Успешный запрос подтверждён') && e.textContent.includes('Последняя проверка'))"))
    ab("screenshot", str(OUT / "desktop-integrations.png"))
    ab("press", "Escape")
    ab("set", "viewport", "390", "844")
    ab("find", "role", "button", "click", "--name", "Ассистент", "--exact")
    check("mobile has no document horizontal overflow", js("document.documentElement.scrollWidth <= innerWidth"))
    ab("scrollintoview", ".qa-assistant-message:last-child .context-source")
    ab("screenshot", str(OUT / "mobile-weather.png"))
    ab("find", "role", "button", "click", "--name", "Настройки и приватность", "--exact")
    wait("document.querySelectorAll('.integration').length > 10")
    open_integration("Open-Meteo")
    check("mobile source links have 44px targets", js("[...document.querySelectorAll('.integration[open] a')].every(e=>e.getBoundingClientRect().height>=44)"))
    ab("screenshot", str(OUT / "mobile-integrations.png"))
    check("no removed decorative slogans returned", js("!['Astana, at your pace.','Your location. Your control.','Source-backed places. Your preferences, your choice.'].some(t=>document.body.innerText.includes(t))"))
    evidence["bundle"] = js("[...document.scripts].find(s=>s.type==='module')?.src.split('/').pop()")


if __name__ == "__main__":
    error = None
    try:
        main()
    except Exception as exc:
        error = str(exc)
    source_paths = ["src/App.tsx", "src/components/ContextSources.tsx", "src/components/IntegrationsPanel.tsx", "src/components/PlacePhoto.tsx", "src/components/OpenUIResponse.tsx", "src/lib/integration-copy.ts", "src/index.css", "src/styles/openui.css"]
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "method": "agent-browser, actual production frontend/FastAPI and live keyless weather/calendar; responses observed without stubbing", "checks": checks, "passed": sum(x["passed"] for x in checks), "total": len(checks), "complete": error is None, "error": error, "evidence": evidence,
              "dataset_sha256": hashlib.sha256((ROOT / "data/pois.json").read_bytes()).hexdigest(),
              "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in source_paths},
              "screenshots": [str(p.relative_to(ROOT)) for p in sorted(OUT.glob("*.png"))], "visual_review": "pending"}
    (ROOT / "artifacts/city-context-ui-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("passed", "total", "complete", "error")}, ensure_ascii=False))
    if error:
        raise SystemExit(1)
