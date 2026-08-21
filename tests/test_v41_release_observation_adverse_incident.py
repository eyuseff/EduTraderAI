import re
from pathlib import Path


LOG_PATH = Path("docs/operations/V41_RELEASE_OBSERVATION_LOG.md")
_ISSUE_REFERENCE_RE = re.compile(r"ISSUE #[1-9][0-9]*\Z")
_TRACKED_FIELDS = (
    "Account-active status",
    "Blocking-flag status",
    "AAPL eligibility",
    "Quote freshness",
    "Application observations",
    "Broker observations",
    "Incident summary",
    "Cleanup status",
)
_HEALTHY_VALUES = {
    "Account-active status": "ACTIVE",
    "Blocking-flag status": "CLEAR",
    "AAPL eligibility": "ELIGIBLE",
    "Quote freshness": "FRESH",
    "Application observations": "OBSERVED",
    "Broker observations": "OBSERVED",
    "Incident summary": "NONE",
    "Cleanup status": "CLEAN",
}
_ADVERSE_VALUES = {
    "Account-active status": "INACTIVE",
    "Blocking-flag status": "BLOCKED",
    "AAPL eligibility": "INELIGIBLE",
    "Quote freshness": "STALE",
    "Cleanup status": "UNRESOLVED",
}


def _requires_incident_reference(values: dict[str, str]) -> bool:
    if any(values[field] == adverse for field, adverse in _ADVERSE_VALUES.items()):
        return True
    return any(
        _ISSUE_REFERENCE_RE.fullmatch(values[field]) is not None
        for field in ("Application observations", "Broker observations")
    )


def _section_values(section: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == 2 and cells[0] in _TRACKED_FIELDS:
            values[cells[0]] = cells[1].strip().strip("`")
    return values


def test_adverse_observation_detection_is_fail_closed() -> None:
    assert not _requires_incident_reference(dict(_HEALTHY_VALUES))

    for field, adverse in _ADVERSE_VALUES.items():
        values = dict(_HEALTHY_VALUES)
        values[field] = adverse
        assert _requires_incident_reference(values), field

    for field in ("Application observations", "Broker observations"):
        values = dict(_HEALTHY_VALUES)
        values[field] = "ISSUE #123"
        assert _requires_incident_reference(values), field


def test_numbered_v41_sessions_reference_incidents_for_adverse_findings() -> None:
    raw = LOG_PATH.read_text(encoding="utf-8")
    assert "Cross-field incident tracking is fail-closed" in raw
    assert "`NONE` is non-qualifying" in raw

    matches = list(re.finditer(r"^### Session (\d+)\s*$", raw, flags=re.MULTILINE))

    for index, match in enumerate(matches):
        section_end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        values = _section_values(raw[match.end() : section_end])

        assert set(values) == set(_TRACKED_FIELDS)
        if _requires_incident_reference(values):
            assert _ISSUE_REFERENCE_RE.fullmatch(values["Incident summary"]), (
                f"Session {match.group(1)} adverse/reportable finding must reference "
                "a repository issue in Incident summary"
            )
