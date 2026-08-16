"""Tests for sanitized release verification summary generation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.generate_release_summary import (
    build_release_summary,
    load_release_summary,
    write_release_summary,
)


def verification_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "PASS",
        "command": "make verify",
        "test_count": 512,
        "line_coverage_percent": 90.1,
        "branch_coverage_percent": 75.2,
        "combined_coverage_percent": 86.4,
        "verified_at": "2026-08-16T16:40:00+00:00",
    }
    payload.update(overrides)
    return payload


def test_summary_is_review_only_even_when_verification_passes() -> None:
    summary = build_release_summary(
        verification_payload(),
        source_commit_sha="a" * 40,
    )

    assert summary.verification_status == "PASS"
    assert summary.review_status == "HUMAN_REVIEW_REQUIRED"
    assert summary.human_approval_required is True
    assert summary.source_commit_sha == "a" * 40
    assert summary.combined_coverage_percent == 86.4


def test_summary_does_not_invent_release_approval_fields() -> None:
    summary = build_release_summary(verification_payload()).to_dict()

    assert "approved" not in summary
    assert "release_decision" not in summary
    assert "tag" not in summary
    assert summary["human_approval_required"] is True


def test_markdown_explicitly_disclaims_release_action() -> None:
    markdown = build_release_summary(verification_payload()).to_markdown()

    assert "Human approval required: **yes**" in markdown
    assert "does not approve, tag, publish, deploy, or release" in markdown


def test_write_release_summary_creates_json_and_markdown(tmp_path: Path) -> None:
    verification_path = tmp_path / "verification.json"
    json_path = tmp_path / "release_summary.json"
    markdown_path = tmp_path / "release_summary.md"
    verification_path.write_text(
        json.dumps(verification_payload()),
        encoding="utf-8",
    )

    written = write_release_summary(
        verification_path,
        json_path=json_path,
        markdown_path=markdown_path,
        source_commit_sha="b" * 40,
    )

    json_payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert json_payload == written.to_dict()
    assert json_payload["review_status"] == "HUMAN_REVIEW_REQUIRED"
    assert markdown_path.read_text(encoding="utf-8") == written.to_markdown()


def test_load_rejects_non_object_metadata(tmp_path: Path) -> None:
    path = tmp_path / "verification.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError):
        load_release_summary(path)


def test_schema_rejects_missing_or_extra_fields() -> None:
    missing = verification_payload()
    missing.pop("verified_at")
    with pytest.raises(ValueError, match="schema mismatch"):
        build_release_summary(missing)

    with pytest.raises(ValueError, match="schema mismatch"):
        build_release_summary(verification_payload(secret="must-not-pass"))


@pytest.mark.parametrize("status", ["", "READY", "APPROVED", None])
def test_status_is_strict(status: object) -> None:
    with pytest.raises(ValueError):
        build_release_summary(verification_payload(status=status))


@pytest.mark.parametrize("coverage", [-0.1, 100.1, "90", True])
def test_coverage_values_are_bounded_numeric_or_null(coverage: object) -> None:
    with pytest.raises(ValueError):
        build_release_summary(
            verification_payload(combined_coverage_percent=coverage)
        )


def test_coverage_can_be_absent_for_non_coverage_verify() -> None:
    summary = build_release_summary(
        verification_payload(
            line_coverage_percent=None,
            branch_coverage_percent=None,
            combined_coverage_percent=None,
        )
    )

    assert summary.combined_coverage_percent is None
    assert "not captured" in summary.to_markdown()


def test_source_sha_must_be_full_hexadecimal() -> None:
    for invalid in ("abc", "g" * 40, "a" * 39, "a" * 41):
        with pytest.raises(ValueError):
            build_release_summary(
                verification_payload(),
                source_commit_sha=invalid,
            )
