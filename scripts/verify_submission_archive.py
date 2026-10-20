#!/usr/bin/env python3
"""Audit a built submission ZIP; optionally replay its extracted public dataset.

Run with the existing environment, after packaging:
  .venv/bin/python scripts/verify_submission_archive.py --replay

The required private root .env is read exactly once, solely to discover secret
values for the offline scan. Values and provider responses are never reported.
No archive is created, no provider is contacted and no corpus is refreshed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile
import zipfile

from dotenv import dotenv_values

try:
    from package_submission import (
        ARCHIVE_REPORT, REQUIRED, ROOT, SKIP_PARTS, VIDEO_PATH, VIDEO_REPORT,
        include, sha256_file, validate_video_report,
    )
except ModuleNotFoundError:
    from scripts.package_submission import (
        ARCHIVE_REPORT, REQUIRED, ROOT, SKIP_PARTS, VIDEO_PATH, VIDEO_REPORT,
        include, sha256_file, validate_video_report,
    )

REPLAY_PYTHON = ROOT / ".venv/bin/python"  # Keep the literal venv entrypoint; do not resolve its symlink.
CHUNK_BYTES = 1024 * 1024
MAX_MEMBER_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
SECRET_FIELD = re.compile(r"(?:^|_)(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)(?:_|$)", re.I)
CORE_DIRECTORIES = ("src", "backend", "scripts", "data", "public/photos", "video-demo/src")
CORE_FILES = {
    ".env.example", "package.json", "package-lock.json", "pyproject.toml", "uv.lock",
    "Dockerfile", "compose.yaml", "requirements.lock.txt",
    "artifacts/presentation-ru-slides/manifest.json",
    "artifacts/presentation-ru-verification.json",
    "artifacts/scenarios-and-limits-ru-verification.json",
    "artifacts/video/ru/remotion-edit-manifest.json",
} | {f"artifacts/presentation-ru-slides/slide-{number:02}.png" for number in range(1, 13)}


class VerificationError(ValueError):
    """A public, sanitized verification failure."""


def load_secret_values(root: Path) -> list[bytes]:
    """One private file read; dotenv interpolation and environment mutation off."""
    path = root / ".env"
    if not path.is_file():
        raise VerificationError("Required private .env is missing; secret scan cannot run")
    content = path.read_text(encoding="utf-8")
    values = dotenv_values(stream=io.StringIO(content), interpolate=False)
    secrets = {value.encode("utf-8") for name, value in values.items() if SECRET_FIELD.search(name) and value}
    if not secrets:
        raise VerificationError("Required private .env contains no configured secrets to scan")
    return sorted(secrets, key=len, reverse=True)


def redact(value, secrets: list[bytes]):
    """Defend reports even if a public filename itself accidentally contains a key."""
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret.decode("utf-8"), "[redacted]")
        return value
    if isinstance(value, dict):
        return {redact(key, secrets): redact(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, secrets) for item in value]
    return value


def forbidden_member(relative: str) -> bool:
    path = PurePosixPath(relative)
    if any(part.lower() in {p.lower() for p in SKIP_PARTS | {".cache", ".presentation-build", ".scenarios-build"}} for part in path.parts):
        return True
    name = path.name.lower()
    if name.startswith(".env") and relative != ".env.example":
        return True
    if path.suffix.lower() in {".log", ".pyc", ".db", ".sqlite", ".sqlite3", ".zip"} or any(marker in name for marker in (".log.", ".sqlite", ".db-")):
        return True
    if relative.startswith("data/raw/") and path.suffix.lower() == ".html":
        return True
    return relative == ARCHIVE_REPORT


def validate_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members, seen, total = [], set(), 0
    if len(archive.infolist()) > 10_000:
        raise VerificationError("Archive has too many entries")
    for info in archive.infolist():
        path = PurePosixPath(info.filename)
        parts = path.parts
        if ("\\" in info.filename or path.is_absolute() or not parts or parts[0] != "qala"
                or ".." in parts or ":" in info.filename
                or any(ord(char) < 32 for char in info.orig_filename)
                or info.filename.rstrip("/") != path.as_posix()):
            raise VerificationError("Unsafe archive member path")
        if info.filename.casefold() in seen:
            raise VerificationError("Duplicate archive member path")
        seen.add(info.filename.casefold())
        if stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1:
            raise VerificationError("Symlink or encrypted archive member")
        relative = "/".join(parts[1:])
        if relative and forbidden_member(relative):
            raise VerificationError("Excluded private, runtime, log or operator HTML file in archive")
        if info.is_dir():
            continue
        if not relative:
            raise VerificationError("Archive root must be a directory")
        total += info.file_size
        if info.file_size > MAX_MEMBER_BYTES or total > MAX_ARCHIVE_BYTES:
            raise VerificationError("Archive exceeds bounded verification size")
        members.append(info)
    return members


def scan_stream(stream, secrets: list[bytes]) -> tuple[str, bool]:
    digest, tail, found = hashlib.sha256(), b"", False
    overlap = max((len(value) for value in secrets), default=1) - 1
    while chunk := stream.read(CHUNK_BYTES):
        digest.update(chunk)
        window = tail + chunk
        found = found or any(secret in window for secret in secrets)
        tail = window[-overlap:] if overlap else b""
    return digest.hexdigest(), found


def scan_pptx(content: bytes, secrets: list[bytes]) -> tuple[int, bool]:
    """PPTX members are compressed, so scan every decompressed part as well."""
    count, found, total = 0, False, 0
    with zipfile.ZipFile(io.BytesIO(content)) as package:
        if len(package.infolist()) > 10_000:
            raise VerificationError("Nested PPTX has too many entries")
        for info in package.infolist():
            total += info.file_size
            if info.file_size > MAX_MEMBER_BYTES or total > MAX_ARCHIVE_BYTES:
                raise VerificationError("Nested PPTX exceeds bounded verification size")
            if info.is_dir():
                continue
            with package.open(info) as stream:
                _, matched = scan_stream(stream, secrets)
            found = found or matched
            count += int(info.filename.lower().endswith((".xml", ".rels")))
    return count, found


def critical_files(root: Path) -> set[str]:
    names = set(REQUIRED) | CORE_FILES
    for directory in CORE_DIRECTORIES:
        for path in (root / directory).rglob("*"):
            if path.is_file() and include(path, root):
                names.add(path.relative_to(root).as_posix())
    return names


def corpus_hashes(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): sha256_file(path)
            for path in sorted((root / "data").rglob("*")) if path.is_file()}


REPLAY_BOOTSTRAP = r'''
import runpy, socket, sys
def denied(*args, **kwargs):
    raise RuntimeError("Network disabled for archive replay")
socket.socket.connect = denied
socket.socket.connect_ex = denied
socket.socket.sendto = denied
socket.create_connection = denied
socket.getaddrinfo = denied
sys.path.insert(0, "scripts")
sys.argv = ["scripts/refresh_dataset.py", "--replay"]
runpy.run_path("scripts/refresh_dataset.py", run_name="__main__")
'''


def replay_archive(archive: zipfile.ZipFile, root: Path) -> dict:
    """Run extracted code/data only, with literal existing Python and no network."""
    if not REPLAY_PYTHON.is_file():
        raise VerificationError("Existing isolated replay Python is missing")
    workspace_before = corpus_hashes(root)
    with tempfile.TemporaryDirectory(prefix="qala-archive-replay-") as directory:
        archive.extractall(directory)  # Paths and symlinks were checked first.
        extracted = Path(directory) / "qala"
        before = corpus_hashes(extracted)
        env = {key: value for key, value in os.environ.items() if not SECRET_FIELD.search(key)}
        env.update(PYTHONDONTWRITEBYTECODE="1", QALA_LLM_PROVIDER="local", QALA_RERANK_PROVIDER="none",
                   HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", PYTHONNOUSERSITE="1")
        try:
            result = subprocess.run([str(REPLAY_PYTHON), "-I", "-B", "-c", REPLAY_BOOTSTRAP], cwd=extracted,
                                    env=env, capture_output=True, text=True, timeout=90, check=False)
        except subprocess.TimeoutExpired as error:
            raise VerificationError("Isolated archive replay timed out") from error
        # Never publish stdout/stderr on failure: an unexpected dependency can
        # include environment or source snippets in an exception message.
        if result.returncode:
            raise VerificationError("Isolated archive replay failed; private output suppressed")
        try:
            evidence = json.loads(result.stdout)
        except (ValueError, UnicodeError) as error:
            raise VerificationError("Isolated archive replay returned invalid evidence") from error
        if before != corpus_hashes(extracted) or workspace_before != corpus_hashes(root):
            raise VerificationError("Dataset changed during isolated archive replay")
        if (evidence.get("mode") != "offline-replay" or evidence.get("dataset_preserved") is not True
                or evidence.get("sha256") != before.get("data/pois.json")):
            raise VerificationError("Isolated archive replay evidence does not match archived dataset")
        return {"status": "passed", "python": str(REPLAY_PYTHON), "network": "socket access blocked",
                "isolated_extracted_project": True, "workspace_and_extracted_data_unchanged": True,
                "dataset_sha256": evidence["sha256"], "coverage": evidence.get("coverage")}


def verify_archive(path: Path, root: Path, secrets: list[bytes], *, replay: bool = False) -> dict:
    report = {"status": "failed", "checked_at": datetime.now(timezone.utc).isoformat(),
              "archive": {"path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size},
              "checks": {}, "secret_scan": {"private_env_read_once": True, "secret_value_count": len(secrets),
                                           "raw_values_reported": False}}
    with zipfile.ZipFile(path) as archive:
        members = validate_members(archive)
        checks = report["checks"]
        checks["safe_paths_and_exclusions"] = True
        hashes, matches, xml_parts = {}, [], 0
        for info in members:
            relative = info.filename.removeprefix("qala/")
            with archive.open(info) as stream:
                digest, found = scan_stream(stream, secrets)
            found = found or any(secret in info.filename.encode("utf-8") for secret in secrets)
            hashes[relative] = digest
            if relative.lower().endswith(".pptx"):
                count, nested_match = scan_pptx(archive.read(info), secrets)
                xml_parts += count
                found = found or nested_match
            if found:
                matches.append(relative)
        # ZipExtFile checks CRC while each entire member is read above.
        checks["all_member_crc_valid"] = True
        report["archive"]["file_count"] = len(members)
        report["secret_scan"].update(scanned_members=len(members), nested_pptx_xml_parts=xml_parts,
                                     matched_members=matches)
        checks["no_private_secret_values"] = not matches
        required = set(REQUIRED) | CORE_FILES
        checks["required_deliverables_present_nonempty"] = all(
            name in hashes and archive.getinfo("qala/" + name).file_size > 0 for name in required)
        # Bind the entire archive to the frozen public workspace before any
        # extracted Python is executed. Extra modules could otherwise shadow
        # imports when the replay adds the archived scripts directory to sys.path.
        expected = {file.relative_to(root).as_posix() for file in root.rglob("*")
                    if file.is_file() and include(file, root)}
        workspace_hashes = {name: sha256_file(root / name) for name in expected & hashes.keys()}
        public_missing = sorted(expected - hashes.keys())
        public_extra = sorted(hashes.keys() - expected)
        public_changed = sorted(name for name in workspace_hashes if workspace_hashes[name] != hashes[name])
        checks["exact_public_workspace_manifest"] = not public_missing and not public_extra and not public_changed
        report["public_manifest"] = {"expected_files": len(expected), "missing": public_missing,
                                     "unexpected": public_extra, "mismatched": public_changed}
        critical = critical_files(root)
        absent = sorted(critical - hashes.keys())
        mismatched = sorted(name for name in critical & hashes.keys()
                            if workspace_hashes.get(name) != hashes[name])
        checks["critical_workspace_hashes_match"] = not absent and not mismatched
        report["critical_files"] = {"count": len(critical), "missing": absent, "mismatched": mismatched,
                                    "sha256": {name: hashes[name] for name in sorted(critical & hashes.keys())}}
        try:
            video_report = json.loads(archive.read("qala/" + VIDEO_REPORT))
            validate_video_report(video_report, hashes.get(VIDEO_PATH, ""))
            checks["final_video_verified_and_digest_matches"] = True
        except (KeyError, ValueError, TypeError, AttributeError, UnicodeError):
            checks["final_video_verified_and_digest_matches"] = False
        if replay and all(checks.values()):
            report["replay"] = replay_archive(archive, root)
            checks["isolated_offline_dataset_replay"] = True
        else:
            report["replay"] = {"status": "not_requested" if not replay else "blocked_by_failed_checks"}
        report["status"] = "verified" if all(checks.values()) else "failed"
    return redact(report, secrets)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", nargs="?", type=Path, default=ROOT / "artifacts/qala-submission.zip")
    parser.add_argument("--replay", action="store_true", help="Run archived dataset --replay in a temporary project with network blocked")
    args = parser.parse_args()
    output = ROOT / ARCHIVE_REPORT
    secrets = []
    try:
        secrets = load_secret_values(ROOT)  # The only private .env read.
        report = verify_archive(args.archive.resolve(), ROOT, secrets, replay=args.replay)
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as error:
        # Report only our controlled diagnostics, never third-party error text.
        message = str(error) if isinstance(error, VerificationError) else type(error).__name__
        report = {"status": "failed", "checked_at": datetime.now(timezone.utc).isoformat(),
                  "error": message, "secret_scan": {"raw_values_reported": False}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(redact(report, secrets), ensure_ascii=False, indent=2) + "\n")
    print("Submission archive verification: " + report["status"])
    print("Report: " + str(output))
    if report["status"] != "verified":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
