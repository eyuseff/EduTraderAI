import re
from datetime import datetime, timedelta
from pathlib import Path


README_PATH = Path("README.md")
DOCS_README_PATH = Path("docs/README.md")
PLAN_PATH = Path("docs/operations/V41_STABLE_PROMOTION_PLAN.md")
LOG_PATH = Path("docs/operations/V41_RELEASE_OBSERVATION_LOG.md")


REQUIRED_SESSION_FIELDS = (
    "Session start UTC",
    "Session end UTC",
    "Observed commit",
    "Environment",
    "Account-active status",
    "Blocking-flag status",
    "AAPL eligibility",
    "Quote freshness",
    "Application observations",
    "Broker observations",
    "Incident summary",
    "Cleanup status",
)
PLACEHOLDER_SESSION_VALUES = {"-", "TBD", "TODO", "N/A", "NA", "UNKNOWN"}


def _table_rows(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 2 or cells[0] in {"Item", "---"}:
            continue
        rows[cells[0]] = cells[1]
    return rows


def _normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def _parse_utc_timestamp(value: str) -> datetime:
    text = value.strip().strip("`")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None, f"timestamp must be timezone-aware: {value!r}"
    assert parsed.utcoffset() == timedelta(0), f"timestamp must be UTC: {value!r}"
    return parsed


def test_v41_observation_log_release_identity_matches_promotion_plan() -> None:
    plan_rows = _table_rows(PLAN_PATH)
    log_rows = _table_rows(LOG_PATH)

    for key in (
        "Release candidate",
        "RC commit",
        "RC published UTC",
        "Minimum elapsed observation",
        "Minimum separate Paper-market sessions",
        "Earliest Stable review",
    ):
        assert log_rows[key] == plan_rows[key]


def test_v41_observation_status_matches_promotion_plan() -> None:
    plan_rows = _table_rows(PLAN_PATH)
    log_rows = _table_rows(LOG_PATH)

    for key in (
        "Post-RC Paper-market sessions",
        "Incidents",
        "Recommendation",
    ):
        assert log_rows[key] == plan_rows[key]


def test_v41_observation_log_remains_fail_closed_about_session_credit() -> None:
    source = _normalized(LOG_PATH)

    assert (
        "No post-RC Paper-market session is credited merely because CI, repository "
        "checks, or the pre-RC Connected Alpaca Paper qualification passed."
    ) in source
    assert "A session does not require an order" in source
    assert (
        "no order may be submitted, replaced, or cancelled merely to satisfy the "
        "observation quota"
    ) in source
    assert "Do not infer broker-side observations from repository or CI state." in source
    assert (
        "Credentials, account identifiers, broker order identifiers, raw broker "
        "payloads, and unredacted logs must never be committed or published."
    ) in source


def test_v41_observation_log_defines_complete_redacted_session_record_shape() -> None:
    raw = LOG_PATH.read_text(encoding="utf-8")
    source = _normalized(LOG_PATH)

    for field in REQUIRED_SESSION_FIELDS:
        assert f"| {field} |" in raw

    assert (
        "This table is a recording contract only; it is not session evidence and does "
        "not itself create session credit."
    ) in source
    assert "A session is not countable if any required field is absent" in source
    assert (
        "Do not increment the session count until a completed, redacted numbered "
        "session section is appended"
    ) in source
    assert "this template does not require or authorize an order" in source
    assert (
        "every required field must be recorded as exactly one two-cell Markdown table row"
        in source
    )
    assert "Blank values and placeholders" in source
    for placeholder in PLACEHOLDER_SESSION_VALUES:
        assert f"`{placeholder}`" in raw


def test_v41_observation_count_matches_numbered_evidence_sections() -> None:
    raw = LOG_PATH.read_text(encoding="utf-8")
    status = _table_rows(LOG_PATH)["Post-RC Paper-market sessions"]
    match = re.fullmatch(r"(\d+) of 5 recorded", status)

    assert match is not None
    recorded_count = int(match.group(1))
    session_numbers = [
        int(value)
        for value in re.findall(r"^### Session (\d+)\s*$", raw, flags=re.MULTILINE)
    ]

    assert session_numbers == list(range(1, len(session_numbers) + 1))
    assert recorded_count == len(session_numbers)
    assert recorded_count <= 5

    source = _normalized(LOG_PATH)
    assert "Counted evidence sections must use the exact heading form `### Session N`" in source
    assert (
        "The `Post-RC Paper-market sessions` status above must equal the number of "
        "those completed numbered sections"
    ) in source


def test_each_numbered_v41_session_contains_every_required_evidence_field() -> None:
    raw = LOG_PATH.read_text(encoding="utf-8")
    matches = list(re.finditer(r"^### Session (\d+)\s*$", raw, flags=re.MULTILINE))

    for index, match in enumerate(matches):
        section_end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        section = raw[match.end() : section_end]

        for field in REQUIRED_SESSION_FIELDS:
            assert section.count(field) == 1, (
                f"Session {match.group(1)} must contain required field {field!r} exactly once"
            )


def test_each_numbered_v41_session_has_substantive_table_values() -> None:
    raw = LOG_PATH.read_text(encoding="utf-8")
    matches = list(re.finditer(r"^### Session (\d+)\s*$", raw, flags=re.MULTILINE))

    for index, match in enumerate(matches):
        section_end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        section = raw[match.end() : section_end]
        values: dict[str, str] = {}

        for line in section.splitlines():
            if not line.startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) != 2 or cells[0] not in REQUIRED_SESSION_FIELDS:
                continue
            assert cells[0] not in values, (
                f"Session {match.group(1)} repeats required field {cells[0]!r}"
            )
            values[cells[0]] = cells[1]

        assert set(values) == set(REQUIRED_SESSION_FIELDS), (
            f"Session {match.group(1)} must record every required field as a two-cell table row"
        )
        for field in REQUIRED_SESSION_FIELDS:
            value = values[field].strip()
            assert value, f"Session {match.group(1)} field {field!r} must not be blank"
            assert value.strip("`").upper() not in PLACEHOLDER_SESSION_VALUES, (
                f"Session {match.group(1)} field {field!r} must not use a placeholder"
            )


def test_each_numbered_v41_session_is_post_rc_and_time_ordered() -> None:
    raw = LOG_PATH.read_text(encoding="utf-8")
    rc_published = _parse_utc_timestamp(_table_rows(PLAN_PATH)["RC published UTC"])
    matches = list(re.finditer(r"^### Session (\d+)\s*$", raw, flags=re.MULTILINE))

    for index, match in enumerate(matches):
        section_end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        section = raw[match.end() : section_end]
        values: dict[str, str] = {}

        for line in section.splitlines():
            if not line.startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) != 2 or cells[0] not in {"Session start UTC", "Session end UTC"}:
                continue
            values[cells[0]] = cells[1]

        start = _parse_utc_timestamp(values["Session start UTC"])
        end = _parse_utc_timestamp(values["Session end UTC"])
        assert start >= rc_published, (
            f"Session {match.group(1)} must start at or after RC publication"
        )
        assert end > start, f"Session {match.group(1)} end must be later than start"


def test_repository_entrypoint_distinguishes_v41_log_from_v40_history() -> None:
    source = _normalized(README_PATH)

    assert (
        "[v4.1 release observation log]"
        "(docs/operations/V41_RELEASE_OBSERVATION_LOG.md)"
    ) in source
    assert (
        "historical [v4.0 observation log]"
        "(docs/operations/RELEASE_OBSERVATION_LOG.md)"
    ) in source
    assert "does not count toward the v4.1 Stable gate" in source


def test_docs_readme_is_an_index_not_a_competing_status_source() -> None:
    source = _normalized(DOCS_README_PATH)

    assert (
        "this file is a documentation index, not the authoritative release-status record"
        in source
    )
    assert "[root README](../README.md)" in source
    assert "`v4.1.0-rc1` **Paper-only** release-candidate observation window" in source
    assert "[v4.1 Stable promotion plan](operations/V41_STABLE_PROMOTION_PLAN.md)" in source
    assert "[v4.1 release observation log](operations/V41_RELEASE_OBSERVATION_LOG.md)" in source
    assert "historical or design context" in source
    assert (
        "No order may be submitted, replaced, or cancelled merely to satisfy the "
        "observation quota."
    ) in source
