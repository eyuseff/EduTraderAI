import re
from pathlib import Path


PLAN_PATH = Path("docs/operations/V41_STABLE_PROMOTION_PLAN.md")
LOG_PATH = Path("docs/operations/V41_RELEASE_OBSERVATION_LOG.md")
_ISSUE_REFERENCE_RE = re.compile(r"ISSUE #[1-9][0-9]*\Z")


def _table_value(path: Path, key: str) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == 2 and cells[0] == key:
            return cells[1].strip().strip("`").strip("*")
    raise AssertionError(f"missing {key!r} row in {path}")


def _session_incident_references(raw: str) -> tuple[str, ...]:
    matches = list(re.finditer(r"^### Session (\d+)\s*$", raw, flags=re.MULTILINE))
    references: list[str] = []

    for index, match in enumerate(matches):
        section_end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        section = raw[match.end() : section_end]
        incident_summary: str | None = None

        for line in section.splitlines():
            if not line.startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) == 2 and cells[0] == "Incident summary":
                incident_summary = cells[1].strip().strip("`")
                break

        assert incident_summary is not None
        if _ISSUE_REFERENCE_RE.fullmatch(incident_summary):
            references.append(incident_summary)

    return tuple(references)


def _incident_status_is_consistent(status: str, references: tuple[str, ...]) -> bool:
    if references:
        return status != "None recorded"
    return status == "None recorded"


def test_incident_status_consistency_rule_is_fail_closed() -> None:
    assert _incident_status_is_consistent("None recorded", ())
    assert not _incident_status_is_consistent("None recorded", ("ISSUE #123",))
    assert _incident_status_is_consistent("See session issue references", ("ISSUE #123",))
    assert not _incident_status_is_consistent("See session issue references", ())


def test_v41_status_cannot_claim_no_incidents_when_sessions_reference_issues() -> None:
    raw = LOG_PATH.read_text(encoding="utf-8")
    references = _session_incident_references(raw)
    log_status = _table_value(LOG_PATH, "Incidents")
    plan_status = _table_value(PLAN_PATH, "Incidents")

    assert log_status == plan_status
    assert _incident_status_is_consistent(log_status, references), (
        "v4.1 Incidents status must say 'None recorded' only when no numbered "
        "session references an incident issue"
    )
