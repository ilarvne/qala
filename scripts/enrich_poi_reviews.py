#!/usr/bin/env python3
"""Import real, signed, openly licensed Mangrove reviews by exact OSM identity.

Ratings are optional evidence, never invented. A 70/100 source rating is shown
as 3.5/5 with the original scale retained. Rating-only reviews have no text.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.mangrove.reviews"
LICENSE_URLS = {"CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/", "CC-BY-SA-4.0": "https://creativecommons.org/licenses/by-sa/4.0/"}


def b64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def verify_review(record: dict) -> bool:
    """Verify the server's returned payload against its actual ES256 JWT."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

    try:
        encoded_header, encoded_payload, encoded_signature = record["jwt"].split(".")
        header = json.loads(b64(encoded_header))
        payload = json.loads(b64(encoded_payload))
        returned = dict(record["payload"])
        signed = dict(payload)
        # The current API canonicalizes the geo subject's parameter order in
        # its presentation payload. Compare equivalent URIs, then verify the
        # untouched original JWT bytes; never sign reconstructed JSON.
        def subject(value):
            uri = urlsplit(value)
            return uri.scheme, uri.netloc, uri.path, sorted(parse_qsl(uri.query)), uri.fragment
        if subject(signed.pop("sub", "")) != subject(returned.pop("sub", "")):
            return False
        if header.get("alg") != "ES256" or signed != returned or header.get("kid") != record["kid"]:
            return False
        signature = b64(encoded_signature)
        if len(signature) != 64 or encoded_signature != record["signature"]:
            return False
        pem = record["kid"].replace("-----BEGIN PUBLIC KEY-----", "").replace("-----END PUBLIC KEY-----", "").strip()
        pem = "-----BEGIN PUBLIC KEY-----\n" + "\n".join(pem[i:i + 64] for i in range(0, len(pem), 64)) + "\n-----END PUBLIC KEY-----\n"
        key = serialization.load_pem_public_key(pem.encode())
        if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
            return False
        der = encode_dss_signature(int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big"))
        key.verify(der, (encoded_header + "." + encoded_payload).encode(), ec.ECDSA(hashes.SHA256()))
        return True
    except (ValueError, KeyError, TypeError, InvalidSignature):
        return False


def distance_m(lat1, lon1, lat2, lon2):
    a, b = math.radians(lat1), math.radians(lat2)
    x = math.sin((b - a) / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371000 * 2 * math.atan2(math.sqrt(x), math.sqrt(max(0, 1 - x)))


def enrich_reviews(dataset: dict, raw: dict, observed: str) -> None:
    by_id = {poi["id"]: poi for poi in dataset["pois"]}
    rejected, accepted, seen = [], [], set()
    for record in raw.get("reviews", []):
        payload = record.get("payload", {})
        metadata = payload.get("metadata", {})
        signature = record.get("signature")
        if not signature or signature in seen:
            continue
        seen.add(signature)
        if not verify_review(record):
            rejected.append({"signature": signature, "reason": "invalid signature or payload mismatch"}); continue
        identity = re.fullmatch(r"(node|way|relation)/(\d+)(?:/\d+)?", metadata.get("osm_id", ""))
        poi = by_id.get("osm-" + "-".join(identity.groups())) if identity else None
        if not poi:
            rejected.append({"signature": signature, "reason": "no exact OSM identity in collected city dataset"}); continue
        if metadata.get("is_generated") is True or payload.get("action"):
            rejected.append({"signature": signature, "reason": "generated content or non-review action"}); continue
        coords = record.get("geo", {}).get("coordinates", {})
        if coords and distance_m(poi["lat"], poi["lon"], coords["lat"], coords["lon"]) > 500:
            rejected.append({"signature": signature, "reason": "review location contradicts OSM identity"}); continue
        license_name = metadata.get("license", "CC-BY-4.0")
        rating = payload.get("rating")
        if license_name not in LICENSE_URLS or not isinstance(rating, (int, float)) or isinstance(rating, bool) or not 0 <= rating <= 100:
            rejected.append({"signature": signature, "reason": "unsupported license or invalid rating"}); continue
        fingerprint = hashlib.sha256(record["kid"].encode()).hexdigest()
        author = metadata.get("nickname") or metadata.get("preferred_username") or "Mangrove contributor " + fingerprint[:10]
        source_url = API + "/review/" + signature
        review = {
            "id": "mangrove-" + signature, "author": author, "author_name": author,
            "author_fingerprint": fingerprint, "author_url": None,
            "text": payload.get("opinion") or None, "rating": round(rating / 20, 2),
            "original_rating": rating, "original_scale": 100,
            "published_at": datetime.fromtimestamp(payload["iat"], timezone.utc).isoformat(),
            "provider": "Mangrove / Open Reviews", "source_url": source_url,
            "license": license_name, "license_url": LICENSE_URLS[license_name],
            "attribution": f"{author} · Mangrove / Open Reviews · {license_name}",
            "subject_uri": payload["sub"], "signature_verified": True,
            "observed_at": observed, "is_affiliated": metadata.get("is_affiliated"),
            "is_personal_experience": metadata.get("is_personal_experience"),
        }
        poi["reviews"] = [r for r in poi.get("reviews", []) if r.get("id") != review["id"]] + [review]
        ratings = [r["rating"] for r in poi["reviews"] if r.get("provider") == "Mangrove / Open Reviews"]
        poi["rating"] = round(sum(ratings) / len(ratings), 2)
        poi["rating_count"] = len(ratings)
        poi["review_count"] = len(poi["reviews"])
        poi["rating_source"] = {"name": "Mangrove / Open Reviews", "url": source_url,
                                "collected_at": observed, "original_scale": 100, "normalized_scale": 5,
                                "aggregation": "Arithmetic mean of exact-OSM-matched signed public ratings, divided by 20; not a Google/2GIS rating", "license": license_name}
        accepted.append({"poi_id": poi["id"], "signature": signature, "text_available": bool(review["text"])})
    dataset["metadata"]["reviews_enrichment"] = {"provider": "Mangrove / Open Reviews", "collected_at": observed,
        "api_url": API + "/geo", "source_review_count": len(raw.get("reviews", [])),
        "matched_review_count": len(accepted), "text_review_count": sum(r["text_available"] for r in accepted),
        "pois_with_rating": len({r["poi_id"] for r in accepted}), "matched": accepted, "rejected": rejected,
        "terms_url": "https://mangrove.reviews/terms", "standard_url": "https://mangrove.reviews/standard",
        "matching": "Exact metadata.osm_id plus location consistency; ES256 signature verified locally; no guessed venue matches"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Replay an existing signed Mangrove response")
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/pois.json")
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text())
    observed = datetime.now(timezone.utc).isoformat()
    if args.input:
        raw = json.loads(args.input.read_text())
    else:
        south, west, north, east = dataset["metadata"]["bbox"]
        response = httpx.get(API + "/geo", params={"xmin": west, "ymin": south, "xmax": east, "ymax": north},
                             timeout=30, headers={"User-Agent": "QalaResearch/2.0 (open city dataset collection)"})
        response.raise_for_status()
        raw = response.json()
        (ROOT / "data/raw/mangrove-astana-bbox.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2))
    enrich_reviews(dataset, raw, observed)
    from collect_pois import coverage, write_json
    dataset["metadata"]["coverage"] = coverage(dataset["pois"])
    write_json(args.dataset, dataset)
    write_json(ROOT / "data/review-attributions.json", {"metadata": dataset["metadata"]["reviews_enrichment"], "reviews": [{"poi_id": p["id"], "poi_name": p["name"], **r} for p in dataset["pois"] for r in p.get("reviews", [])]})
    print(json.dumps(dataset["metadata"]["reviews_enrichment"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
