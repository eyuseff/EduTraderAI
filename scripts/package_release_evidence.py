"""Build and verify a local, sanitized release evidence bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import string
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "docs/releases/release-evidence-manifest-v4.1.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "build/release_evidence.zip"

_FORBIDDEN_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(rb"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(
        rb"(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|password)"
        rb"\s*[:=]\s*[\"']?[^\s\"']{8,}"
    ),
)


def _safe_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(f"unsafe evidence path: {value!r}")
    return path


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in string.hexdigits for character in value)
    )


def load_manifest(path: Path) -> tuple[str, ...]:
    """Load the checked-in evidence manifest using a strict schema."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("evidence manifest must be a JSON object")
    if set(payload) != {"schema_version", "review_status", "required_files"}:
        raise ValueError("evidence manifest schema mismatch")
    if payload["schema_version"] != 1:
        raise ValueError("unsupported evidence manifest schema version")
    if payload["review_status"] != "HUMAN_REVIEW_REQUIRED":
        raise ValueError("evidence manifest must preserve human review")
    required_files = payload["required_files"]
    if not isinstance(required_files, list) or not required_files:
        raise ValueError("required_files must be a non-empty list")
    if any(not isinstance(item, str) for item in required_files):
        raise ValueError("required_files entries must be strings")
    normalized = tuple(str(_safe_relative_path(item)) for item in required_files)
    if len(set(normalized)) != len(normalized):
        raise ValueError("required_files must not contain duplicates")
    return normalized


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _assert_redacted(path: str, data: bytes) -> None:
    for pattern in _FORBIDDEN_PATTERNS:
        if pattern.search(data):
            raise ValueError(f"possible secret detected in evidence file: {path}")


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def _write_entry(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    archive.writestr(_zip_info(name), data)


def build_evidence_pack(
    project_root: Path,
    manifest_path: Path,
    output_path: Path,
) -> dict[str, object]:
    """Package required evidence locally and verify all copied checksums."""

    required_files = load_manifest(manifest_path)
    records: list[dict[str, object]] = []
    payloads: dict[str, bytes] = {}
    root = project_root.resolve()

    for relative in required_files:
        source = project_root / relative
        if source.is_symlink():
            raise ValueError(f"evidence file must not be a symlink: {relative}")
        resolved = source.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as error:
            raise ValueError(
                f"evidence file escapes project root: {relative}"
            ) from error
        if not source.is_file():
            raise ValueError(f"required evidence file is missing: {relative}")
        data = source.read_bytes()
        _assert_redacted(relative, data)
        payloads[relative] = data
        records.append(
            {
                "path": relative,
                "sha256": _sha256(data),
                "size_bytes": len(data),
            }
        )

    resolved_manifest = {
        "files": records,
        "review_status": "HUMAN_REVIEW_REQUIRED",
        "schema_version": 1,
    }
    manifest_bytes = (
        json.dumps(resolved_manifest, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    sums_bytes = "".join(
        f"{record['sha256']}  {record['path']}\n" for record in records
    ).encode("utf-8")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w") as archive:
        for relative in required_files:
            _write_entry(archive, relative, payloads[relative])
        _write_entry(archive, "evidence-manifest.json", manifest_bytes)
        _write_entry(archive, "SHA256SUMS", sums_bytes)

    verify_evidence_pack(output_path)
    archive_digest = _sha256(output_path.read_bytes())
    output_path.with_suffix(output_path.suffix + ".sha256").write_text(
        f"{archive_digest}  {output_path.name}\n",
        encoding="utf-8",
    )
    return resolved_manifest


def verify_evidence_pack(bundle_path: Path) -> None:
    """Fail closed if any bundled evidence differs from its resolved manifest."""

    try:
        with zipfile.ZipFile(bundle_path, "r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError("evidence bundle contains duplicate entries")
            manifest = json.loads(archive.read("evidence-manifest.json"))
            sums = archive.read("SHA256SUMS").decode("utf-8")
            if not isinstance(manifest, dict) or set(manifest) != {
                "files",
                "review_status",
                "schema_version",
            }:
                raise ValueError("resolved evidence manifest schema mismatch")
            if manifest["schema_version"] != 1:
                raise ValueError("resolved evidence manifest version mismatch")
            if manifest["review_status"] != "HUMAN_REVIEW_REQUIRED":
                raise ValueError("resolved evidence manifest lost human review")
            records = manifest["files"]
            if not isinstance(records, list):
                raise ValueError("resolved evidence manifest is invalid")
            expected_names = {"evidence-manifest.json", "SHA256SUMS"}
            expected_sum_lines: list[str] = []
            for record in records:
                if not isinstance(record, dict):
                    raise ValueError("resolved evidence record is invalid")
                if set(record) != {"path", "sha256", "size_bytes"}:
                    raise ValueError("resolved evidence record schema mismatch")
                path = record["path"]
                digest = record["sha256"]
                size_bytes = record["size_bytes"]
                if not isinstance(path, str) or not _is_sha256(digest):
                    raise ValueError("resolved evidence record types are invalid")
                if not isinstance(size_bytes, int) or isinstance(size_bytes, bool):
                    raise ValueError("resolved evidence size is invalid")
                _safe_relative_path(path)
                data = archive.read(path)
                _assert_redacted(path, data)
                if len(data) != size_bytes or _sha256(data) != digest.lower():
                    raise ValueError(f"evidence checksum mismatch: {path}")
                expected_names.add(path)
                expected_sum_lines.append(f"{digest}  {path}\n")
            if set(names) != expected_names:
                raise ValueError(
                    "evidence bundle contains unexpected or missing entries"
                )
            if sums != "".join(expected_sum_lines):
                raise ValueError("SHA256SUMS does not match resolved evidence manifest")
    except (KeyError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        raise ValueError("invalid evidence bundle") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    try:
        build_evidence_pack(PROJECT_ROOT, arguments.manifest, arguments.output)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"RELEASE EVIDENCE PACK FAILED: {error}")
        return 1
    print(f"Release evidence pack created: {arguments.output}")
    print("Human review remains required; no upload, push, tag, or release occurred.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
