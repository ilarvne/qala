#!/usr/bin/env python3
"""Package source and final artifacts; exclude credentials, databases and caches."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/qala-submission.zip"
REQUIRED = {
    "README.md", "data/pois.json", "video-demo/src/Root.tsx",
    "artifacts/presentation-ru.pptx", "artifacts/presentation-ru.pdf",
    "artifacts/video/ru/qala-demo-ru.mp4", "artifacts/video/ru/qala-demo-ru.srt",
    "docs/pitch-script-ru.md", "docs/test-scenarios-ru.md",
    "artifacts/scenarios-and-limits-ru.pdf",
    "artifacts/video/ru/final-export-verification.json",
}
SKIP_PARTS = {"node_modules", ".venv", ".git", "__pycache__", ".pytest_cache", ".local", "work", "private", "logs", "rejected-preview", "media-upgrade-staging", "data-expansion-staging"}
TOP = {"README.md", "AGENTS.md", "LICENSE", "PRODUCT.md", "DESIGN.md", "Dockerfile", "compose.yaml", "package.json", "package-lock.json", "pyproject.toml", "uv.lock", "requirements.txt", "requirements.lock.txt", "components.json", "index.html", "vite.config.ts", "tsconfig.json", "tsconfig.app.json", "tsconfig.node.json", ".env.example", ".gitignore", ".dockerignore"}
DIRECTORIES = {"src", "backend", "scripts", "data", "docs", "public", "artifacts", ".github", "video-demo"}
VIDEO_PATH = "artifacts/video/ru/qala-demo-ru.mp4"
VIDEO_REPORT = "artifacts/video/ru/final-export-verification.json"
ARCHIVE_REPORT = "artifacts/submission-archive-verification.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_video_report(report: dict, video_sha256: str) -> None:
    """Reject technical-only reports, stale exports and unreviewed renders."""
    if not isinstance(report, dict) or report.get("status") != "verified":
        raise ValueError("Final Russian video has not completed verification")
    output = report.get("output", {})
    if not isinstance(output, dict) or output.get("path") != VIDEO_PATH or output.get("sha256") != video_sha256:
        raise ValueError("Final Russian video does not match its verified digest")
    checks = report.get("checks", {})
    if not isinstance(checks, dict) or not checks or any(value is not True for value in checks.values()):
        raise ValueError("Final Russian video has incomplete technical checks")
    review = report.get("visual_review", {})
    if (not isinstance(review, dict) or review.get("status") != "passed"
            or not isinstance(review.get("frames"), list) or not review["frames"]):
        raise ValueError("Final Russian video has not completed visual review")


def validate_required_deliverables(root: Path = ROOT) -> None:
    for name in sorted(REQUIRED):
        required = root / name
        if not required.is_file() or required.stat().st_size == 0:
            raise ValueError("Required current deliverable is missing: " + name)
    try:
        report = json.loads((root / VIDEO_REPORT).read_text())
    except (ValueError, UnicodeError) as error:
        raise ValueError("Final Russian video verification report is invalid") from error
    validate_video_report(report, sha256_file(root / VIDEO_PATH))


def include(path: Path, root: Path = ROOT) -> bool:
    relative = path.relative_to(root)
    if any(part in SKIP_PARTS for part in relative.parts):
        return False
    if path.is_symlink() or path == root / "artifacts/qala-submission.zip" or relative.as_posix() == ARCHIVE_REPORT:
        return False
    if path.suffix.lower() in {".log", ".pyc", ".sqlite", ".sqlite3", ".db", ".zip", ".sha256"} or any(marker in path.name.lower() for marker in (".log.", ".sqlite", ".db-")):
        return False
    if path.name.startswith(".env") and relative.as_posix() != ".env.example":
        return False
    # Whole operator pages are local evidence caches, not redistributable assets.
    # Source URLs, dates, hashes and normalized schedule facts are in pois.json.
    if relative.parts[:2] == ("data", "raw") and path.suffix == ".html":
        return False
    return len(relative.parts) == 1 and path.name in TOP or relative.parts[0] in DIRECTORIES


def main():
    try:
        validate_required_deliverables()
    except ValueError as error:
        raise SystemExit(str(error)) from error
    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(ROOT.rglob("*")):
            if path.is_file() and include(path):
                archive.write(path, "qala/" + path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(OUTPUT) as archive:
        names = archive.namelist()
        assert "qala/README.md" in names and "qala/.env.example" in names
        assert all("qala/" + name in names for name in REQUIRED)
        assert not any(name.endswith("/.env") or "/node_modules/" in name or ".sqlite" in name for name in names)
        assert archive.testzip() is None
    digest = sha256_file(OUTPUT)
    (ROOT / "artifacts/qala-submission.sha256").write_text(f"{digest}  qala-submission.zip\n")
    print(f"Packaged {len(names)} files, {OUTPUT.stat().st_size / 1024**2:.1f} MiB: {OUTPUT}")
    print(f"SHA-256: {digest}")


if __name__ == "__main__":
    main()
