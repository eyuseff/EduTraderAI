"""Generate sanitized human-review release summaries from verification metadata."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]

_REQUIRED_VERIFICATION_FIELDS = {
    "status",
    "command",
    "test_count",
    "line_coverage_percent",
    "branch_coverage_percent",
    "combined_coverage_percent",
    "verified_at",
}
_ALLOWED_STATUS = {"PASS", "FAIL"}


@dataclass(frozen=True, slots=True)
class ReleaseVerificationSummary:
    """Secret-free verification readout that never makes a release decision."""

    verification_status: str
    review_status: str
    command: str
    test_count: int
    line_coverage_percent: float | None
    branch_coverage_percent: float | None
    combined_coverage_percent: float | None
    verified_at: str
    source_commit_sha: str | None = None
    human_approval_required: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "verification_status": self.verification_status,
            "review_status": self.review_status,
            "command": self.command,
            "test_count": self.test_count,
            "line_coverage_percent": self.line_coverage_percent,
            "branch_coverage_percent": self.branch_coverage_percent,
            "combined_coverage_percent": self.combined_coverage_percent,
            "verified_at": self.verified_at,
            "source_commit_sha": self.source_commit_sha,
            "human_approval_required": self.human_approval_required,
        }

    def to_markdown(self) -> str:
        coverage = (
            "not captured"
            if self.combined_coverage_percent is None
            else f"{self.combined_coverage_percent:.1f}% combined"
        )
        source = self.source_commit_sha or "not supplied"
        return (
            "# EduTraderAI Release Verification Summary\n\n"
            f"- Verification status: **{self.verification_status}**\n"
            f"- Review status: **{self.review_status}**\n"
            f"- Verification command: `{self.command}`\n"
            f"- Collected tests: **{self.test_count}**\n"
            f"- Coverage: **{coverage}**\n"
            f"- Verified at: `{self.verified_at}`\n"
            f"- Source commit: `{source}`\n"
            "- Human approval required: **yes**\n\n"
            "This summary reports verification evidence only. It does not approve, "
            "tag, publish, deploy, or release any build.\n"
        )


def build_release_summary(
    verification: Mapping[str, object], *, source_commit_sha: str | None = None
) -> ReleaseVerificationSummary:
    """Validate sanitized verification metadata and build a review-only summary."""

    if set(verification) != _REQUIRED_VERIFICATION_FIELDS:
        missing = sorted(_REQUIRED_VERIFICATION_FIELDS - set(verification))
        extra = sorted(set(verification) - _REQUIRED_VERIFICATION_FIELDS)
        raise ValueError(f"verification schema mismatch; missing={missing}, extra={extra}")

    status = verification["status"]
    command = verification["command"]
    test_count = verification["test_count"]
    verified_at = verification["verified_at"]
    if not isinstance(status, str) or status not in _ALLOWED_STATUS:
        raise ValueError("verification status must be PASS or FAIL")
    if command != "make verify":
        raise ValueError("verification command must be 'make verify'")
    if isinstance(test_count, bool) or not isinstance(test_count, int) or test_count < 0:
        raise ValueError("test_count must be a non-negative integer")
    if not isinstance(verified_at, str) or not verified_at.strip():
        raise ValueError("verified_at must be a non-empty string")

    coverage_values: list[float | None] = []
    for field in (
        "line_coverage_percent",
        "branch_coverage_percent",
        "combined_coverage_percent",
    ):
        value = verification[field]
        if value is None:
            coverage_values.append(None)
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field} must be numeric or null")
        normalized = float(value)
        if not 0 <= normalized <= 100:
            raise ValueError(f"{field} must be between 0 and 100")
        coverage_values.append(normalized)

    normalized_sha = _normalize_optional_sha(source_commit_sha)
    return ReleaseVerificationSummary(
        verification_status=status,
        review_status="HUMAN_REVIEW_REQUIRED",
        command=command,
        test_count=test_count,
        line_coverage_percent=coverage_values[0],
        branch_coverage_percent=coverage_values[1],
        combined_coverage_percent=coverage_values[2],
        verified_at=verified_at,
        source_commit_sha=normalized_sha,
        human_approval_required=True,
    )


def load_release_summary(
    verification_path: Path, *, source_commit_sha: str | None = None
) -> ReleaseVerificationSummary:
    if not isinstance(verification_path, Path):
        raise TypeError("verification_path must be a Path")
    payload = json.loads(verification_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("verification metadata must be a JSON object")
    return build_release_summary(payload, source_commit_sha=source_commit_sha)


def write_release_summary(
    verification_path: Path,
    *,
    json_path: Path,
    markdown_path: Path,
    source_commit_sha: str | None = None,
) -> ReleaseVerificationSummary:
    """Write deterministic local summary artifacts; never mutate release state."""

    summary = load_release_summary(
        verification_path, source_commit_sha=source_commit_sha
    )
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(summary.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(summary.to_markdown(), encoding="utf-8")
    return summary


def _normalize_optional_sha(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("source_commit_sha must be a string or None")
    normalized = value.strip().lower()
    if len(normalized) != 40 or any(character not in "0123456789abcdef" for character in normalized):
        raise ValueError("source_commit_sha must be a 40-character hexadecimal SHA")
    return normalized


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verification",
        type=Path,
        default=PROJECT_ROOT / "build/verification.json",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=PROJECT_ROOT / "build/release_summary.json",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=PROJECT_ROOT / "build/release_summary.md",
    )
    parser.add_argument("--source-commit-sha")
    arguments = parser.parse_args()
    try:
        write_release_summary(
            arguments.verification,
            json_path=arguments.json_output,
            markdown_path=arguments.markdown_output,
            source_commit_sha=arguments.source_commit_sha,
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(f"RELEASE SUMMARY GENERATION FAILED: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
