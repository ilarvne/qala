"""Grounded OpenUI programs: layout choices never become arbitrary HTML or facts.

The frontend registers this small vocabulary with @openuidev/react-lang. Place
nodes reference only IDs in this response; facts remain in the sourced payload.
"""
from __future__ import annotations

import json
import re


def build_openui(result: dict, message: str = "") -> dict:
    places = result.get("recommendations", [])[:3]
    ids = [str(place["id"]) for place in places]
    compare = len(ids) > 1 and bool(re.search(r"compar|versus|\bvs\b|сравн|салыстыр", message, re.I))
    layout = "comparison" if compare else "clarification" if not ids and result.get("clarifications") else "itinerary"
    children: list[str] = []
    statements: list[str] = []
    if ids:
        children.append("summary")
        statements.append("summary = TripSummary()")
        children.append("places")
        if compare:
            statements.append("places = Comparison(" + json.dumps(ids, ensure_ascii=False) + ")")
        else:
            refs = []
            for index, place_id in enumerate(ids):
                ref = f"place{index}"
                encoded = json.dumps(place_id, ensure_ascii=False)
                statements.append(f"{ref} = PlaceOption({encoded}, @SelectPlace({encoded}), @InspectPlace({encoded}), @SavePlace({encoded}))")
                refs.append(ref)
            statements.append("places = Itinerary([" + ", ".join(refs) + "])")
    if result.get("clarifications"):
        children.append("questions")
        statements.append("questions = Clarifications()")
    children.append("controls")
    statements.append("controls = PlanControls(@ApplyPreferences())")
    if result.get("followups"):
        children.append("followups")
        statements.append("followups = FollowUps()")
    document = "root = CityResponse([" + ", ".join(children) + "])\n" + "\n".join(statements)
    return {"version": 1, "format": "openui-lang", "layout": layout, "document": document}
