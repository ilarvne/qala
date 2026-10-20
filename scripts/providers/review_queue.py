"""Offline editorial review hints, never automatic POI imports or status edits."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import math
from pathlib import PurePosixPath
import re

from scripts.providers.common import distance_m, local_names, normalized_name, public_url, source_url


def safe_csv_cell(value):
    """Keep spreadsheet programs from executing source text as a formula."""
    if isinstance(value, str) and (value.startswith(("\t", "\r", "\n"))
                                  or value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@"))):
        return "'" + value
    return value


def _source(value):
    if not isinstance(value, dict):
        return None
    return {"name": value.get("name"), "url": public_url(value.get("url")),
            "updated_at": value.get("updated_at"), "collected_at": value.get("collected_at")}


def _local(poi):
    source = _source(poi.get("source"))
    return {"id": poi["id"], "name": poi.get("name"), "category": poi.get("category"),
            "lat": poi.get("lat"), "lon": poi.get("lon"), "address": poi.get("address"),
            "hours": poi.get("hours"), "hours_source": _source(poi.get("hours_source")),
            "last_edit": source.get("updated_at") if source else None,
            "recommendable": poi.get("recommendable") if isinstance(poi.get("recommendable"), bool) else None,
            "source": source}


def _observation(row):
    fields = ("provider", "provider_id", "name", "source_url", "lat", "lon", "address", "rating", "rating_scale",
              "rating_count", "review_count", "observed_at", "access_method", "http_status", "evidence_sha256",
              "photo_source_links", "review_source_links", "import_policy")
    return {key: list(row[key]) if isinstance(row.get(key), list) else row.get(key) for key in fields}


def _coordinate(value, lower, upper):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and lower <= value <= upper


def _candidates(row, pois, maximum_distance_m=200):
    if row.get("access_method") == "exa" or not _coordinate(row.get("lat"), -90, 90) or not _coordinate(row.get("lon"), -180, 180):
        return []
    target = normalized_name(row["name"])
    result = []
    for poi in pois:
        if not _coordinate(poi.get("lat"), -90, 90) or not _coordinate(poi.get("lon"), -180, 180):
            continue
        aliases = local_names(poi)
        # Whole normalized name containment is a suggestion only. Avoid matching
        # a substring inside another word, e.g. "Cafe" inside "Cafela".
        related = [name for name in aliases if name and target and
                   (name == target or " " + name + " " in " " + target + " "
                    or " " + target + " " in " " + name + " ")]
        if not related:
            continue
        delta = distance_m(row["lat"], row["lon"], poi["lat"], poi["lon"])
        if delta <= maximum_distance_m:
            result.append({"local_poi": _local(poi), "distance_m": round(delta, 1),
                           "name_relation": "exact_normalized_name" if target in aliases else "normalized_name_containment",
                           "resolution_state": "manual_review", "assigned": False})
    return sorted(result, key=lambda item: (item["distance_m"], item["local_poi"]["id"]))[:10]


def _evidence_file(value):
    if not isinstance(value, str) or "\\" in value:
        return None
    path = PurePosixPath(value)
    return str(path) if not path.is_absolute() and ".." not in path.parts and path.parts and path.parts[0] == "artifacts" else None


def _status_source(conflict):
    source = conflict.get("provider_observation")
    if not isinstance(source, dict) or source.get("provider") not in {"google", "2gis", "yandex"}:
        raise ValueError("Status conflict requires a recognized provider observation")
    url = source_url(source.get("source_url"), source["provider"])
    try:
        acquired = datetime.fromisoformat(source["observed_at"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Status conflict requires its original acquisition time") from exc
    digest = source.get("evidence_sha256")
    if not url or acquired.tzinfo is None or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("Status conflict lacks a public source or evidence digest")
    return {"provider": source["provider"], "name": source.get("name"), "source_url": url,
            "observed_at": source["observed_at"], "evidence_sha256": digest,
            "reported_status": source.get("reported_status"), "evidence_path": _evidence_file(source.get("evidence_path")),
            "import_policy": "evaluation_only"}


def build_review_queue(rows, pois, quality_conflicts=()):
    """Build source-backed manual review work from already sanitized observations.

    Exact assignments come exclusively from the upstream strict correlator.
    Candidates never become assignments, and differences between independent
    rating populations are reported separately from editorial status conflicts.
    """
    by_id = {poi["id"]: poi for poi in pois}
    items = []
    for row in rows:
        if row.get("matched_poi_ids"):
            continue
        candidates = _candidates(row, pois)
        items.append({"id": "identity:" + row["provider"] + ":" + row["provider_id"],
                      "kind": "identity_resolution", "priority": "medium" if candidates else "low",
                      "resolution_state": "manual_review", "reason": "No unique exact local name and nearby entity-coordinate match.",
                      "provider_observation": _observation(row), "local_pois": [], "candidate_pois": candidates,
                      "matched_poi_ids": [], "evidence_links": [row["source_url"]],
                      "required_action": "Check current operator identity and address; candidate suggestions are not assignments.",
                      "import_policy": "evaluation_only"})

    for conflict in quality_conflicts:
        if not isinstance(conflict, dict) or conflict.get("kind") != "operating_status_conflict":
            continue
        status = _status_source(conflict)
        evidence_rows = [row for row in rows if row["provider"] == status["provider"] and row["source_url"] == status["source_url"]]
        same_acquisition = next((row for row in evidence_rows if row["observed_at"] == status["observed_at"]), None)
        if same_acquisition:
            # Retain the closure evidence digest/time, while including metrics
            # and references only when acquired in that same source capture.
            status = {**_observation(same_acquisition), **status}
        if "provider_id" not in status:
            identifiers = {row["provider_id"] for row in evidence_rows}
            status["provider_id"] = next(iter(identifiers)) if len(identifiers) == 1 else None
        for field in ("rating", "rating_count", "review_count", "rating_scale"):
            status.setdefault(field, None)
        for field in ("photo_source_links", "review_source_links"):
            status.setdefault(field, [])
        # A claimed POI ID in a conflict file is not sufficient proof. Require
        # the same provider entity to have a current exact local correlation.
        exact_ids = {identifier for row in evidence_rows for identifier in row.get("matched_poi_ids", [])}
        claimed = conflict.get("matched_poi_ids") if isinstance(conflict.get("matched_poi_ids"), list) else []
        local_ids = sorted(identifier for identifier in claimed if identifier in exact_ids and identifier in by_id)
        related = [_local(by_id[identifier]) for identifier in local_ids]
        links = [status["source_url"]]
        if status["evidence_path"]:
            links.append(status["evidence_path"])
        links.extend(poi["source"]["url"] for poi in related if poi["source"] and poi["source"]["url"])
        identifier = conflict.get("id")
        identifier = identifier[:250] if isinstance(identifier, str) else status["provider"] + ":" + status["evidence_sha256"][:16]
        items.append({"id": "status:" + identifier, "kind": "operating_status_conflict", "priority": "high",
                      "resolution_state": "manual_review", "reason": "Provider reports an operating status that needs independent operator verification; the local corpus has not been changed.",
                      "provider_observation": status, "related_observations": [_observation(row) for row in evidence_rows],
                      "matched_poi_ids": local_ids, "local_pois": related, "candidate_pois": [],
                      "independent_operator_confirmation": conflict.get("independent_operator_confirmation") is True,
                      "identity_verified_by_current_audit": bool(local_ids), "evidence_links": list(dict.fromkeys(links)),
                      "required_action": "Verify the current operator's status and identity before making any editorial change.",
                      "import_policy": "evaluation_only"})

    groups = defaultdict(list)
    for row in rows:
        for identifier in row.get("matched_poi_ids", []):
            if identifier in by_id:
                groups[identifier].append(row)
    comparisons = []
    for identifier, observations in sorted(groups.items()):
        differences = []
        for field in ("rating", "rating_count", "review_count"):
            values = [{"provider": row["provider"], "provider_id": row["provider_id"], "value": row.get(field),
                       "observed_at": row["observed_at"], "source_url": row["source_url"]} for row in observations]
            known = {item["value"] for item in values if item["value"] is not None}
            if len(known) > 1:
                differences.append({"field": field, "observations": values,
                                    "interpretation": "Independent provider audiences and acquisition times; values are not pooled or treated as the same votes."})
        comparisons.append({"local_poi": _local(by_id[identifier]), "resolution_state": "evaluation_only",
                            "provider_observations": [_observation(row) for row in observations],
                            "disagreements": differences, "rating_aggregation_performed": False,
                            "status_review_ids": [item["id"] for item in items if item["kind"] == "operating_status_conflict" and identifier in item["matched_poi_ids"]]})
    items.sort(key=lambda item: ({"high": 0, "medium": 1, "low": 2}[item["priority"]], item["id"]))
    return {"schema_version": 1, "scope": "Retained provider evaluation observations only; not a citywide coverage or quality assessment.",
            "import_policy": "evaluation_only", "dataset_modified": False, "network_requests": 0,
            "items": items, "matched_poi_comparisons": comparisons,
            "counts": {"manual_review_items": len(items), "unmatched_observations": sum(item["kind"] == "identity_resolution" for item in items),
                       "operating_status_conflicts": sum(item["kind"] == "operating_status_conflict" for item in items),
                       "candidate_suggestions": sum(len(item["candidate_pois"]) for item in items),
                       "exact_matched_pois_compared": len(comparisons),
                       "pois_with_independent_provider_metric_differences": sum(bool(item["disagreements"]) for item in comparisons)}}


def review_csv_rows(queue):
    """One row per manual item, with JSON arrays preserving ambiguous candidates."""
    import json

    for item in queue["items"]:
        observation = item["provider_observation"]
        related = item["local_pois"] or [candidate["local_poi"] for candidate in item["candidate_pois"]]
        row = {key: observation.get(key) for key in ("provider", "provider_id", "name", "source_url", "observed_at", "rating", "rating_scale", "rating_count", "review_count", "evidence_sha256")}
        row.update({key: item[key] for key in ("id", "kind", "priority", "resolution_state", "reason", "required_action")})
        row.update(matched_poi_ids=json.dumps(item["matched_poi_ids"], ensure_ascii=False),
                   local_pois=json.dumps(related, ensure_ascii=False), candidate_pois=json.dumps(item["candidate_pois"], ensure_ascii=False),
                   photo_source_links=json.dumps(observation.get("photo_source_links", []), ensure_ascii=False),
                   review_source_links=json.dumps(observation.get("review_source_links", []), ensure_ascii=False),
                   evidence_links=json.dumps(item["evidence_links"], ensure_ascii=False), import_policy="evaluation_only")
        yield {key: safe_csv_cell(value) for key, value in row.items()}


REVIEW_CSV_FIELDS = ["id", "kind", "priority", "resolution_state", "reason", "required_action", "provider", "provider_id", "name",
                     "source_url", "observed_at", "rating", "rating_scale", "rating_count", "review_count", "evidence_sha256",
                     "matched_poi_ids", "local_pois", "candidate_pois", "photo_source_links", "review_source_links", "evidence_links", "import_policy"]


def comparison_csv_rows(queue):
    """Keep each provider's metrics, time and evidence in a separate CSV row."""
    import json

    for comparison in queue["matched_poi_comparisons"]:
        local = comparison["local_poi"]
        for observation in comparison["provider_observations"]:
            row = {key: observation.get(key) for key in ("provider", "provider_id", "name", "rating", "rating_scale", "rating_count", "review_count", "source_url", "observed_at", "evidence_sha256")}
            row.update(local_poi_id=local["id"], local_name=local["name"], local_hours=local["hours"], local_last_edit=local["last_edit"],
                       local_recommendable=local["recommendable"], resolution_state="evaluation_only",
                       photo_source_links=json.dumps(observation["photo_source_links"], ensure_ascii=False),
                       review_source_links=json.dumps(observation["review_source_links"], ensure_ascii=False),
                       disagreements=json.dumps(comparison["disagreements"], ensure_ascii=False),
                       status_review_ids=json.dumps(comparison["status_review_ids"], ensure_ascii=False), rating_aggregation_performed=False)
            yield {key: safe_csv_cell(value) for key, value in row.items()}


COMPARISON_CSV_FIELDS = ["local_poi_id", "local_name", "local_hours", "local_last_edit", "local_recommendable", "resolution_state",
                         "provider", "provider_id", "name", "rating", "rating_scale", "rating_count", "review_count", "source_url",
                         "observed_at", "evidence_sha256", "photo_source_links", "review_source_links", "disagreements", "status_review_ids", "rating_aggregation_performed"]
