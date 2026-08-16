from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from scripts.package_release_evidence import build_evidence_pack, verify_evidence_pack


def _write_manifest(root: Path, required_files: list[str]) -> Path:
    manifest = root / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "required_files": required_files,
                "review_status": "HUMAN_REVIEW_REQUIRED",
                "schema_version": 1,
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_build_evidence_pack_is_self_contained_and_hashed(tmp_path: Path) -> None:
    build = tmp_path / "build"
    build.mkdir()
    first = build / "verification.json"
    second = build / "release_summary.md"
    first.write_text('{"status":"PASS"}\n', encoding="utf-8")
    second.write_text("# Review\nHUMAN_REVIEW_REQUIRED\n", encoding="utf-8")
    manifest = _write_manifest(
        tmp_path,
        ["build/verification.json", "build/release_summary.md"],
    )
    output = build / "evidence.zip"

    resolved = build_evidence_pack(tmp_path, manifest, output)

    assert resolved["review_status"] == "HUMAN_REVIEW_REQUIRED"
    verify_evidence_pack(output)
    with zipfile.ZipFile(output) as archive:
        assert set(archive.namelist()) == {
            "build/verification.json",
            "build/release_summary.md",
            "evidence-manifest.json",
            "SHA256SUMS",
        }
    sidecar = output.with_suffix(".zip.sha256").read_text(encoding="utf-8")
    assert sidecar.startswith(hashlib.sha256(output.read_bytes()).hexdigest())


def test_build_evidence_pack_rejects_possible_secret(tmp_path: Path) -> None:
    build = tmp_path / "build"
    build.mkdir()
    evidence = build / "verification.json"
    evidence.write_text(
        '{"api_key":"sk-abcdefghijklmnopqrstuv"}\n',
        encoding="utf-8",
    )
    manifest = _write_manifest(tmp_path, ["build/verification.json"])

    with pytest.raises(ValueError, match="possible secret detected"):
        build_evidence_pack(tmp_path, manifest, build / "evidence.zip")


def test_build_evidence_pack_rejects_unsafe_manifest_path(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, ["../outside.json"])

    with pytest.raises(ValueError, match="unsafe evidence path"):
        build_evidence_pack(tmp_path, manifest, tmp_path / "evidence.zip")


def test_verify_evidence_pack_rejects_checksum_tampering(tmp_path: Path) -> None:
    output = tmp_path / "tampered.zip"
    data = b"safe evidence\n"
    wrong_digest = "0" * 64
    resolved = {
        "files": [
            {
                "path": "build/verification.json",
                "sha256": wrong_digest,
                "size_bytes": len(data),
            }
        ],
        "review_status": "HUMAN_REVIEW_REQUIRED",
        "schema_version": 1,
    }
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("build/verification.json", data)
        archive.writestr(
            "evidence-manifest.json",
            json.dumps(resolved),
        )
        archive.writestr(
            "SHA256SUMS",
            f"{wrong_digest}  build/verification.json\n",
        )

    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_evidence_pack(output)
