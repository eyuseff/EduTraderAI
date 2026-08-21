import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


LOG_PATH = Path("docs/operations/V41_RELEASE_OBSERVATION_LOG.md")


def _parse_utc_timestamp(value: str) -> datetime:
    text = value.strip().strip("`")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None, f"timestamp must be timezone-aware: {value!r}"
    assert parsed.utcoffset() == timedelta(0), f"timestamp must be UTC: {value!r}"
    return parsed


def _assert_completed_by_revision(session_end: datetime, revision_time: datetime) -> None:
    assert session_end <= revision_time, (
        "completed observation evidence cannot end after the repository revision "
        "that records and validates it"
    )


def _head_commit_time() -> datetime:
    result = subprocess.run(
        ["git", "show", "-s", "--format=%cI", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return _parse_utc_timestamp(result.stdout.strip())


def test_completed_observation_evidence_rejects_future_end_time() -> None:
    revision_time = datetime(2026, 8, 21, 20, 0, tzinfo=timezone.utc)

    _assert_completed_by_revision(revision_time, revision_time)
    _assert_completed_by_revision(revision_time - timedelta(seconds=1), revision_time)
    with pytest.raises(AssertionError, match="cannot end after"):
        _assert_completed_by_revision(revision_time + timedelta(seconds=1), revision_time)


def test_numbered_v41_sessions_cannot_end_after_recording_revision() -> None:
    raw = LOG_PATH.read_text(encoding="utf-8")
    revision_time = _head_commit_time()
    matches = list(re.finditer(r"^### Session (\d+)\s*$", raw, flags=re.MULTILINE))

    for index, match in enumerate(matches):
        section_end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        section = raw[match.end() : section_end]
        recorded_end: str | None = None

        for line in section.splitlines():
            if not line.startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) == 2 and cells[0] == "Session end UTC":
                recorded_end = cells[1]
                break

        assert recorded_end is not None, (
            f"Session {match.group(1)} must record Session end UTC before time validation"
        )
        _assert_completed_by_revision(_parse_utc_timestamp(recorded_end), revision_time)
