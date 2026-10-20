#!/usr/bin/env python3
"""Focused production-browser regressions for saved places, memory and estimates."""
import json
from pathlib import Path
from capture_demo import ab, loaded, js, check, checks, BASE_URL, ROOT


def main():
    ab("set", "viewport", "1600", "900")
    ab("open", BASE_URL)
    loaded()
    check("production startup resolves", js('document.querySelectorAll(".place-card").length') > 0)
    name = js('document.querySelector(".place-card h3").textContent')
    ab("click", '.place-card button[aria-label="Save place"]')
    ab("click", '[data-testid="nav-saved"]')
    check("saved place appears in drawer", name in ab("get", "text", "[role=dialog]"))
    ab("find", "role", "button", "click", "--name", "Clear saved places")
    check("saved places can be cleared", "Your next favorite is out there" in ab("get", "text", "[role=dialog]"))
    ab("press", "Escape")
    ab("click", '[data-testid="nav-memory"]')
    ab("click", "#remember")
    ab("wait", "--fn", 'document.querySelector("#remember")?.getAttribute("aria-checked") === "true"')
    db_record = 'fetch("/api/memory/" + sessionStorage.getItem("qala-session")).then(r=>r.json()).then(d=>Boolean(d.preferences))'
    check("memory write reaches server", js(db_record) is True)
    ab("press", "Escape")
    ab("reload")
    loaded()
    ab("click", '[data-testid="nav-memory"]')
    check("reload restores existing memory consent", js('document.querySelector("#remember")?.getAttribute("aria-checked")') == "true")
    ab("find", "role", "button", "click", "--name", "Forget my preferences")
    ab("wait", "--fn", 'document.querySelector("#remember")?.getAttribute("aria-checked") === "false"')
    check("forget deletes server preferences", js(db_record) is False)
    ab("press", "Escape")
    ab("click", '[data-testid="scenario-coffee"]')
    loaded()
    check("coffee produces one stop", js('document.querySelectorAll(".place-card").length') == 1)
    check("socket uncertainty is visible", "Power outlets and quiet seating are not verified" in ab("get", "text", '[data-testid="uncertainty-summary"]'))
    ab("click", '[data-testid="scenario-family"]')
    loaded()
    check("family preset produces corpus places", js('document.querySelectorAll(".place-card").length') > 0)
    ab("click", '[data-testid="nav-route"]')
    check("family route opens itinerary", "Your little adventure" in ab("get", "text", "[role=dialog]"))
    ab("press", "Escape")
    # Observe real outgoing bodies; do not stub or alter network responses.
    js('window.__qalaBodies=[]; const originalFetch=window.fetch; window.fetch=(...args)=>{if(String(args[0]).includes("/api/recommend"))window.__qalaBodies.push(JSON.parse(args[1].body));return originalFetch(...args)}; true')
    ab("click", '[data-testid="scenario-airport"]')
    ab("wait", '[data-testid="empty-response-message"]')
    ab("click", '[aria-label="Your estimated airport transfer time"]')
    ab("find", "role", "option", "click", "--name", "30 min", "--exact")
    ab("wait", "--fn", 'window.__qalaBodies.at(-1)?.airport_transfer_minutes === 30')
    check("airport estimate reaches real API", js('window.__qalaBodies.at(-1).airport_transfer_minutes') == 30)
    ab("click", '[aria-label="Your estimated airport transfer time"]')
    ab("find", "role", "option", "click", "--name", "Choose estimate", "--exact")
    ab("wait", "--fn", 'window.__qalaBodies.at(-1)?.airport_transfer_minutes === null && Boolean(document.querySelector("[data-testid=empty-response-message]"))')
    check("clearing estimate sends null", js('window.__qalaBodies.at(-1).airport_transfer_minutes') is None)
    check("missing-transfer clarification reaches empty UI", "transfer" in ab("get", "text", '[data-testid="empty-response-message"]').lower())
    report = {"method": f"agent-browser, production frontend and real FastAPI at {BASE_URL}; network bodies observed without mocking responses", "checks": checks, "passed": sum(c["passed"] for c in checks), "total": len(checks)}
    (ROOT / "artifacts/browser-flows.json").write_text(json.dumps(report, indent=2))
    print(f"{report['passed']}/{report['total']} browser flow checks passed")
    ab("close")


if __name__ == "__main__":
    main()
