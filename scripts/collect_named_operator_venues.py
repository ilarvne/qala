#!/usr/bin/env python3
"""Stage one exact OSM centre with its separately scoped visitor component.

This is a deliberately bounded offline parser, not a generic venue inference
engine. It never publishes the dataset, requests a network resource, renames
the historical closed Nur Alem entity, or assigns photographs/reviews. Full
operator HTML remains private; portable evidence contains only short excerpts.
"""
from __future__ import annotations

import argparse
import base64
import copy
from datetime import datetime
import hashlib
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

try:
    from scripts.collect_pois import coverage, transform
    from scripts.providers.crawl_state import atomic_json_write
except ModuleNotFoundError:
    from collect_pois import coverage, transform
    from providers.crawl_state import atomic_json_write


ROOT = Path(__file__).resolve().parents[1]
SIDECAR_NAME = "named-operator-venues.json"
OSM_ID = 454857501
VENUE_ID = f"osm-way-{OSM_ID}"
OSM_URL = f"https://www.openstreetmap.org/way/{OSM_ID}"
OSM_API_URL = f"https://www.openstreetmap.org/api/0.6/way/{OSM_ID}/full.json"
OPERATOR_URL = "https://alem.ai/en/"
REFERENCE_POINT = (51.089252, 71.4161925)


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden_depth = 0

    def handle_starttag(self, tag, _attrs):
        if tag in {"script", "style", "noscript", "template"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "template"} and self.hidden_depth:
            self.hidden_depth -= 1

    def handle_data(self, value):
        if not self.hidden_depth:
            self.parts.append(value)


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()


def _digest(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value)


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Original source acquisition time is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid source acquisition time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Source acquisition time requires a timezone")
    return value


def _point(lat, lon):
    if any(isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) for n in (lat, lon)):
        raise ValueError("Finite physical coordinates are required")
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("Physical coordinates are outside Earth bounds")
    return lat, lon


def _distance(a, b):
    lat, other = math.radians(a[0]), math.radians(b[0])
    h = math.sin((other - lat) / 2) ** 2 + math.cos(lat) * math.cos(other) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(max(0, min(1, h))))


def _operator_domain(url):
    if not isinstance(url, str):
        raise ValueError("The exact official operator domain is required")
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.netloc != "alem.ai" or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("The exact official operator domain is required")
    return parts


def _opening_facts(excerpts: list[str]) -> dict:
    if not isinstance(excerpts, list) or not excerpts or any(not isinstance(x, str) or not x.strip() for x in excerpts):
        raise ValueError("Bounded operator excerpts are required")
    if len(" ".join(excerpts).split()) > 25:
        raise ValueError("Operator evidence exceeds the 25-word source excerpt allowance")
    text = " ".join(excerpts)
    opening = re.search(r"\bThe Museum of Singularity\s+is open:\s*(\d{2}:\d{2})\s*[-–—]\s*(\d{2}:\d{2})\s+Tue\s*[-–—]\s*Sun,\s*Mon\s*[-–—]\s*Maintenance day\b", text)
    if not opening:
        raise ValueError("Official source does not explicitly establish the current museum and its opening days")
    start, end = opening.group(1, 2)
    for clock in (start, end):
        hour, minute = (int(piece) for piece in clock.split(":"))
        if hour > 23 or minute > 59:
            raise ValueError("Invalid official museum opening time")
    if start >= end:
        raise ValueError("Unsupported or contradictory official opening interval")
    coordinates = re.findall(r"\[\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*\]", text)
    points = {_point(float(lat), float(lon)) for lat, lon in coordinates}
    if len(points) != 1:
        raise ValueError("Exactly one explicit official location is required")
    return {"name": "Museum of Singularity", "hours": f"Tu-Su {start}-{end}; Mo off", "point": list(points.pop())}


def _osm_proof(payload: dict, observed_at: str, body_sha256: str) -> dict:
    _timestamp(observed_at)
    if not _digest(body_sha256) or not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
        raise ValueError("Exact OSM response and acquisition digest are required")
    ways = [element for element in payload["elements"] if element.get("type") == "way" and element.get("id") == OSM_ID]
    if len(ways) != 1:
        raise ValueError("Exactly the explicitly scoped OSM way is required")
    way = ways[0]
    if type(way.get("version")) is not int or way["version"] <= 0:
        raise ValueError("An exact positive OSM element version is required")
    _timestamp(way.get("timestamp"))
    tags = way.get("tags", {})
    if not isinstance(tags, dict) or tags.get("name", "").casefold() != "alem.ai" or tags.get("museum") != "future":
        raise ValueError("OSM identity is not the explicitly linked alem.ai building")
    _operator_domain(tags.get("website"))
    node_ids = way.get("nodes")
    if not isinstance(node_ids, list) or len(node_ids) < 4 or node_ids[0] != node_ids[-1] or any(type(n) is not int for n in node_ids):
        raise ValueError("A complete closed OSM building outline is required")
    nodes = {}
    for node in payload["elements"]:
        if node.get("type") == "node" and node.get("id") in node_ids:
            if node["id"] in nodes:
                raise ValueError("Duplicate OSM node coordinates are ambiguous")
            lat, lon = _point(node.get("lat"), node.get("lon"))
            nodes[node["id"]] = {"type": "node", "id": node["id"], "lat": lat, "lon": lon}
    if set(nodes) != set(node_ids) or len(set(node_ids)) < 3:
        raise ValueError("OSM way node geometry is incomplete")
    minimal = {"elements": [nodes[n] for n in sorted(nodes)] + [{key: copy.deepcopy(way[key]) for key in ("type", "id", "version", "timestamp", "nodes", "tags")}]}
    return {"source_url": OSM_API_URL, "observed_at": observed_at, "body_sha256": body_sha256,
            "parsed_sha256": _hash(_canonical(minimal)), "payload": minimal}


def _candidate(evidence: dict) -> dict:
    if not isinstance(evidence, dict) or set(evidence) != {"osm", "operator"}:
        raise ValueError("Named venue requires exactly its OSM and official operator evidence")
    osm, operator = evidence["osm"], evidence["operator"]
    if not isinstance(osm, dict) or osm.get("source_url") != OSM_API_URL:
        raise ValueError("Unexpected OSM source identity")
    checked_osm = _osm_proof(osm.get("payload"), osm.get("observed_at"), osm.get("body_sha256"))
    if checked_osm != osm:
        raise ValueError("OSM parsed evidence digest or identity differs")
    if not isinstance(operator, dict) or operator.get("url") != OPERATOR_URL or operator.get("final_url") != OPERATOR_URL:
        raise ValueError("Unexpected official operator source")
    _timestamp(operator.get("observed_at"))
    if not _digest(operator.get("body_sha256")) or operator.get("excerpts_sha256") != _hash("\n".join(operator.get("excerpts", [])).encode()):
        raise ValueError("Invalid official source or excerpt digest")
    facts = _opening_facts(operator.get("excerpts"))
    if facts != operator.get("facts"):
        raise ValueError("Parsed museum facts differ from retained official excerpts")
    way = next(item for item in osm["payload"]["elements"] if item["type"] == "way")
    nodes = [item for item in osm["payload"]["elements"] if item["type"] == "node"]
    center = ((min(n["lat"] for n in nodes) + max(n["lat"] for n in nodes)) / 2,
              (min(n["lon"] for n in nodes) + max(n["lon"] for n in nodes)) / 2)
    if _distance(center, facts["point"]) > 200 or _distance(center, REFERENCE_POINT) > 200:
        raise ValueError("OSM building and current operator location do not agree within 200 metres")
    # Reuse the established normalized schema, then restore exact source tags
    # and the whole building's identity. Operator museum facts apply only to a
    # visitor component, never to all offices occupying this OSM footprint.
    normalized = copy.deepcopy(way)
    normalized["center"] = {"lat": center[0], "lon": center[1]}
    normalized["tags"]["tourism"] = "museum"
    poi = transform({"elements": [normalized]}, OSM_API_URL, osm["observed_at"])["pois"][0]
    poi["raw_tags"] = copy.deepcopy(way["tags"])
    poi["aliases"] = sorted({value for key, value in way["tags"].items() if key == "name" or key.startswith("name:")})
    source = {"name": "alem.ai", "url": OPERATOR_URL, "collected_at": operator["observed_at"],
              "observed_at": operator["observed_at"], "body_sha256": operator["body_sha256"],
              "excerpts": copy.deepcopy(operator["excerpts"]), "excerpts_sha256": operator["excerpts_sha256"]}
    poi.update(category="culture", poi_type="architectural_landmark", hours=None,
               tags=["architecture", "culture", "outdoors", "photography", "walk"],
               indoor=False, indoor_evidence="exterior-only recommendation; building interior access not established",
               recommended_action="view_exterior",
               description="Alem.ai artificial intelligence centre, recommended here for viewing its exterior. The Museum of Singularity inside has a separate visitor schedule.",
               description_source=copy.deepcopy(source), description_derived=False,
               category_source=copy.deepcopy(source), additional_sources=[copy.deepcopy(source)],
               visitor_components=[{"name": facts["name"], "poi_type": "museum", "hours": facts["hours"],
                   "operating_status": "open", "source": copy.deepcopy(source),
                   "scope": "Museum of Singularity inside alem.ai; these hours and status do not describe the whole office centre"}])
    poi["source"].update(license="ODbL 1.0", license_url="https://www.openstreetmap.org/copyright",
                         acquisition_url=OSM_API_URL, body_sha256=osm["body_sha256"])
    poi["coordinates_note"] = "Exact OSM building bounding-box centre; museum entrance not verified"
    return poi


def collect_named_operator_venue(osm_payload: dict, operator_page: dict, *, osm_observed_at: str, osm_body_sha256: str) -> dict:
    """Parse acquired evidence only; preserve both original acquisition times."""
    if not isinstance(operator_page, dict) or operator_page.get("source_url") != OPERATOR_URL or operator_page.get("final_url") != OPERATOR_URL:
        raise ValueError("Only the exact official English operator page is supported")
    try:
        body = base64.b64decode(operator_page["html_b64"], validate=True)
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError("Original private operator HTML is required for collection") from exc
    if len(body) > 3_000_000 or _hash(body) != operator_page.get("sha256"):
        raise ValueError("Operator body digest or bounded response size differs")
    parser = _VisibleText()
    parser.feed(body.decode("utf-8", errors="strict"))
    visible = " ".join(" ".join(parser.parts).split())
    opening = re.findall(r"\bThe Museum of Singularity\s+is open:\s*\d{2}:\d{2}\s*[-–—]\s*\d{2}:\d{2}\s+Tue\s*[-–—]\s*Sun,\s*Mon\s*[-–—]\s*Maintenance day\b", visible)
    coordinates = re.findall(r"\[\s*-?\d{1,2}(?:\.\d+)?\s*,\s*-?\d{1,3}(?:\.\d+)?\s*\]", visible)
    if len(set(opening)) != 1 or len(set(coordinates)) != 1:
        raise ValueError("Official museum opening statement or coordinates are missing or ambiguous")
    excerpts = [opening[0], coordinates[0]]
    operator = {"url": OPERATOR_URL, "final_url": operator_page["final_url"], "observed_at": operator_page.get("observed_at"),
                "body_sha256": operator_page["sha256"], "excerpts": excerpts, "excerpts_sha256": _hash("\n".join(excerpts).encode()),
                "facts": _opening_facts(excerpts)}
    evidence = {"osm": _osm_proof(osm_payload, osm_observed_at, osm_body_sha256), "operator": operator}
    return {"schema_version": 1, "venue_id": VENUE_ID, "candidate": _candidate(evidence), "evidence": evidence}


def apply_named_operator_venues(dataset: dict, sidecar: dict) -> dict:
    """Validate first, then add without changing any prior POI or closure."""
    if not isinstance(sidecar, dict) or type(sidecar.get("schema_version")) is not int or sidecar.get("schema_version") != 1 or sidecar.get("venue_id") != VENUE_ID:
        raise ValueError("Unsupported bounded named-operator venue collection")
    candidate = _candidate(sidecar.get("evidence"))
    if candidate != sidecar.get("candidate"):
        raise ValueError("Staged venue facts differ from exact retained evidence")
    matches = [poi for poi in dataset.get("pois", []) if poi.get("id") == VENUE_ID]
    if len(matches) > 1:
        raise ValueError("Duplicate named venue IDs require explicit resolution")
    if matches:
        keys = ("id", "name", "names", "lat", "lon", "category", "poi_type", "hours", "hours_source", "source", "raw_tags", "website", "phone", "address", "recommendable", "operating_status", "indoor", "indoor_evidence", "recommended_action", "visitor_components")
        if any(matches[0].get(key) != candidate.get(key) for key in keys):
            raise ValueError("Existing named venue conflicts with retained operator identity")
    result = copy.deepcopy(dataset)
    if not matches:
        result["pois"].append(candidate)
        result["pois"].sort(key=lambda poi: poi["id"])
    result["metadata"].update(count=len(result["pois"]), coverage=coverage(result["pois"]))
    result["metadata"]["named_operator_collection"] = {"venue_ids": [VENUE_ID], "source_path": "data/raw/" + SIDECAR_NAME,
        "osm_observed_at": sidecar["evidence"]["osm"]["observed_at"], "operator_observed_at": sidecar["evidence"]["operator"]["observed_at"],
        "policy": "Exact separately acquired OSM centre represented for exterior viewing only; official museum-component hours/status stay separate from main aliases/actionable hours and whole-office access; source coordinates agree within 200m; original historical venues preserved"}
    return result


def apply_retained_named_operator_venues(dataset: dict, project_root: Path = ROOT) -> dict:
    path = project_root / "data/raw" / SIDECAR_NAME
    return apply_named_operator_venues(dataset, json.loads(path.read_text())) if path.is_file() else dataset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--osm", required=True, type=Path)
    parser.add_argument("--osm-acquisition", required=True, type=Path)
    parser.add_argument("--operator-page", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / ".local" / SIDECAR_NAME)
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to((ROOT / ".local").resolve()):
        parser.error("Named-venue collection writes only to private .local staging; use the dataset publisher for public output")
    acquisition = json.loads(args.osm_acquisition.read_text())
    raw = args.osm.read_bytes()
    if acquisition.get("source_url") != OSM_API_URL or acquisition.get("http_status") != 200 or acquisition.get("body_sha256") != _hash(raw):
        parser.error("OSM acquisition URL, HTTP status or original body digest differs")
    sidecar = collect_named_operator_venue(json.loads(raw), json.loads(args.operator_page.read_text()),
        osm_observed_at=acquisition.get("observed_at"), osm_body_sha256=acquisition["body_sha256"])
    atomic_json_write(args.output, sidecar)
    print(json.dumps({"venue_id": VENUE_ID, "output": str(args.output), "name": sidecar["candidate"]["name"],
        "hours": sidecar["candidate"]["hours"], "visitor_components": [{key: item[key] for key in ("name", "hours")}
            for item in sidecar["candidate"]["visitor_components"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
