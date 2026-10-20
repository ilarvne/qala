"""Synthetic archive fixtures only: never read real credentials or package files."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import stat
import zipfile

import pytest

from scripts import package_submission as package
from scripts import verify_submission_archive as audit


def pptx_bytes(text: str = "Public slide") -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ppt/slides/slide1.xml", "<slide>" + text + "</slide>")
    return output.getvalue()


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setattr(audit, "CORE_FILES", {".env.example"})
    for relative in package.REQUIRED | {".env.example", "src/main.tsx", "data/pois.json"}:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pptx_bytes() if relative.endswith(".pptx") else b"Public fixture")
    report = {"status": "verified", "output": {"path": package.VIDEO_PATH,
              "sha256": package.sha256_file(root / package.VIDEO_PATH)},
              "checks": {"full_decode": True},
              "visual_review": {"status": "passed", "frames": [{"path": "frame.png"}]}}
    (root / package.VIDEO_REPORT).write_text(json.dumps(report))
    return root


def make_archive(root: Path, path: Path, extra: dict[str, bytes] | None = None) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for file in sorted(root.rglob("*")):
            if file.is_file() and package.include(file, root):
                archive.write(file, "qala/" + file.relative_to(root).as_posix())
        for name, content in (extra or {}).items():
            archive.writestr(name, content)
    return path


def test_valid_synthetic_archive_hashes_and_pptx_scan(project, tmp_path):
    path = make_archive(project, tmp_path / "submission.zip")
    report = audit.verify_archive(path, project, [b"fixture-private-token"])
    assert report["status"] == "verified"
    assert report["secret_scan"]["nested_pptx_xml_parts"] == 1
    assert all(report["checks"].values())
    assert report["replay"]["status"] == "not_requested"


@pytest.mark.parametrize("relative", [
    ".env", "nested/.env.backup", "artifacts/private/key", ".local/preferences.sqlite3",
    "video-demo/node_modules/dependency.js", "artifacts/run.log", "artifacts/requests.db",
    "data/raw/baiterek-operator.html", "artifacts/nested-private.zip",
])
def test_excluded_private_and_operator_files_rejected(project, tmp_path, relative):
    path = make_archive(project, tmp_path / "submission.zip", {"qala/" + relative: b"excluded"})
    with zipfile.ZipFile(path) as archive, pytest.raises(audit.VerificationError):
        audit.validate_members(archive)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "qala/../escape", "qala\\escape", "qala//ambiguous"])
def test_unsafe_member_paths_rejected(tmp_path, name):
    path = tmp_path / "bad.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(name, b"unsafe")
    with zipfile.ZipFile(path) as archive, pytest.raises(audit.VerificationError):
        audit.validate_members(archive)


def test_symlink_member_rejected(tmp_path):
    path = tmp_path / "bad.zip"
    with zipfile.ZipFile(path, "w") as archive:
        info = zipfile.ZipInfo("qala/link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "../../private")
    with zipfile.ZipFile(path) as archive, pytest.raises(audit.VerificationError):
        audit.validate_members(archive)


def test_private_secret_across_stream_chunks_and_redacted_report(project, tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "CHUNK_BYTES", 16)
    secret = b"fixture-private-token"
    path = make_archive(project, tmp_path / "submission.zip",
                        {"qala/artifacts/binary.dat": b"x" * 15 + secret + b"\x00\xff"})
    report = audit.verify_archive(path, project, [secret])
    assert report["status"] == "failed"
    assert report["secret_scan"]["matched_members"] == ["artifacts/binary.dat"]
    assert secret.decode() not in json.dumps(report)


def test_secret_in_compressed_pptx_xml_detected(project, tmp_path):
    secret = b"fixture-private-token"
    (project / "artifacts/presentation-ru.pptx").write_bytes(pptx_bytes(secret.decode()))
    path = make_archive(project, tmp_path / "submission.zip")
    report = audit.verify_archive(path, project, [secret])
    assert report["status"] == "failed"
    assert report["secret_scan"]["matched_members"] == ["artifacts/presentation-ru.pptx"]
    assert secret.decode() not in json.dumps(report)


def test_critical_workspace_change_detected(project, tmp_path):
    path = make_archive(project, tmp_path / "submission.zip")
    (project / "src/main.tsx").write_text("Changed after packaging")
    report = audit.verify_archive(path, project, [b"fixture-private-token"])
    assert report["critical_files"]["mismatched"] == ["src/main.tsx"]
    assert report["status"] == "failed"


def test_unexpected_importable_module_blocks_replay_before_execution(project, tmp_path, monkeypatch):
    path = make_archive(project, tmp_path / "submission.zip", {"qala/scripts/json.py": b"raise RuntimeError('unverified')"})

    def must_not_replay(*args, **kwargs):
        raise AssertionError("Unverified archive was executed")

    monkeypatch.setattr(audit, "replay_archive", must_not_replay)
    report = audit.verify_archive(path, project, [b"fixture-private-token"], replay=True)
    assert report["status"] == "failed"
    assert report["public_manifest"]["unexpected"] == ["scripts/json.py"]
    assert report["replay"]["status"] == "blocked_by_failed_checks"


def test_bad_crc_rejected(project, tmp_path):
    path = make_archive(project, tmp_path / "submission.zip")
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo("qala/README.md")
        offset = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
    content = bytearray(path.read_bytes())
    content[offset] ^= 1
    path.write_bytes(content)
    with pytest.raises(zipfile.BadZipFile):
        audit.verify_archive(path, project, [b"fixture-private-token"])


@pytest.mark.parametrize("change", ["technical_only", "stale_digest", "failed_check", "unreviewed", "empty_pdf"])
def test_package_gate_blocks_unfinished_or_stale_deliverables(project, change):
    report_path = project / package.VIDEO_REPORT
    report = json.loads(report_path.read_text())
    if change == "technical_only":
        report["status"] = "technical_verified"
    elif change == "stale_digest":
        report["output"]["sha256"] = "0" * 64
    elif change == "failed_check":
        report["checks"]["full_decode"] = False
    elif change == "unreviewed":
        report["visual_review"]["status"] = "pending"
    elif change == "empty_pdf":
        (project / "artifacts/scenarios-and-limits-ru.pdf").write_bytes(b"")
    report_path.write_text(json.dumps(report))
    with pytest.raises(ValueError):
        package.validate_required_deliverables(project)


def test_package_gate_accepts_matching_verified_fixture(project):
    package.validate_required_deliverables(project)


def test_secret_file_read_once_without_interpolation(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("EXAMPLE_API_KEY=fixture-${DO_NOT_EXPAND}\nQALA_LLM_PROVIDER=local\n")
    original = Path.read_text
    reads = []

    def tracked_read(self, *args, **kwargs):
        if self == path:
            reads.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", tracked_read)
    assert audit.load_secret_values(tmp_path) == [b"fixture-${DO_NOT_EXPAND}"]
    assert len(reads) == 1


def test_isolated_replay_blocks_socket_and_preserves_both_corpora(tmp_path):
    if not audit.REPLAY_PYTHON.is_file():
        pytest.skip("Existing project Python is unavailable")
    root = tmp_path / "workspace"
    (root / "data").mkdir(parents=True)
    (root / "data/pois.json").write_text('{"fixture":true}')
    digest = hashlib.sha256((root / "data/pois.json").read_bytes()).hexdigest()
    path = tmp_path / "replay.zip"
    code = (
        "import json,socket\n"
        "try:\n socket.create_connection(('127.0.0.1',9))\n"
        "except RuntimeError:\n blocked=True\n"
        "else:\n raise AssertionError('network guard absent')\n"
        f"print(json.dumps({{'mode':'offline-replay','dataset_preserved':True,'sha256':'{digest}',"
        "'coverage':{'network_blocked':blocked}}))\n"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.write(root / "data/pois.json", "qala/data/pois.json")
        archive.writestr("qala/scripts/refresh_dataset.py", code)
    before = audit.corpus_hashes(root)
    with zipfile.ZipFile(path) as archive:
        audit.validate_members(archive)
        report = audit.replay_archive(archive, root)
    assert report["status"] == "passed"
    assert report["coverage"]["network_blocked"] is True
    assert before == audit.corpus_hashes(root)
