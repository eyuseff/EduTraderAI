import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest


PLAN_PATH = Path("docs/operations/V41_STABLE_PROMOTION_PLAN.md")
LOG_PATH = Path("docs/operations/V41_RELEASE_OBSERVATION_LOG.md")


def _table_value(source: str, label: str) -> str:
    match = re.search(
        rf"^\| {re.escape(label)} \| (.+?) \|$",
        source,
        flags=re.MULTILINE,
    )
    assert match is not None, f"missing {label!r} status row"
    return match.group(1).strip().strip("`").strip("*")


def _session_progress(source: str) -> tuple[int, int]:
    value = _table_value(source, "Post-RC Paper-market sessions")
    match = re.fullmatch(r"([0-9]+) of ([0-9]+) recorded", value)
    assert match is not None, f"invalid session progress: {value!r}"
    return int(match.group(1)), int(match.group(2))


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None, f"timestamp must be timezone-aware: {value!r}"
    return parsed.astimezone(timezone.utc)


def _head_commit_time() -> datetime:
    result = subprocess.run(
        ["git", "show", "-s", "--format=%cI", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return _parse_utc(result.stdout.strip())


def _assert_ready_only_after_prerequisites(
    *,
    recorded: int,
    required: int,
    revision_time: datetime,
    earliest_review: datetime,
    recommendation: str,
) -> None:
    if recommendation != "READY FOR FINAL REVIEW":
        return

    assert recorded >= required, (
        "READY FOR FINAL REVIEW requires all post-RC Paper-market sessions"
    )
    assert revision_time >= earliest_review, (
        "READY FOR FINAL REVIEW cannot precede the earliest Stable review"
    )


def test_ready_recommendation_fails_closed_before_prerequisites() -> None:
    earliest = datetime(2026, 8, 27, 17, 20, 13, tzinfo=timezone.utc)

    with pytest.raises(AssertionError, match="requires all post-RC"):
        _assert_ready_only_after_prerequisites(
            recorded=4,
            required=5,
            revision_time=earliest,
            earliest_review=earliest,
            recommendation="READY FOR FINAL REVIEW",
        )

    with pytest.raises(AssertionError, match="cannot precede"):
        _assert_ready_only_after_prerequisites(
            recorded=5,
            required=5,
            revision_time=earliest.replace(day=26),
            earliest_review=earliest,
            recommendation="READY FOR FINAL REVIEW",
        )

    _assert_ready_only_after_prerequisites(
        recorded=5,
        required=5,
        revision_time=earliest,
        earliest_review=earliest,
        recommendation="READY FOR FINAL REVIEW",
    )


def test_current_v41_recommendation_cannot_claim_early_readiness() -> None:
    plan = PLAN_PATH.read_text(encoding="utf-8")
    log = LOG_PATH.read_text(encoding="utf-8")
    earliest_review = _parse_utc(_table_value(plan, "Earliest Stable review"))
    revision_time = _head_commit_time()

    for source in (plan, log):
        recorded, required = _session_progress(source)
        recommendation = _table_value(source, "Recommendation")
        _assert_ready_only_after_prerequisites(
            recorded=recorded,
            required=required,
            revision_time=revision_time,
            earliest_review=earliest_review,
            recommendation=recommendation,
        )
