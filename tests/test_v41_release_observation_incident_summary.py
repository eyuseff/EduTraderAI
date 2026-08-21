import re
from pathlib import Path


LOG_PATH = Path("docs/operations/V41_RELEASE_OBSERVATION_LOG.md")
_INCIDENT_REFERENCE_RE = re.compile(r"(?:NONE|ISSUE #[1-9][0-9]*)\Z")


def test_numbered_v41_sessions_require_reference_only_incident_summary() -> None:
    raw = LOG_PATH.read_text(encoding="utf-8")
    assert "must record exactly `NONE`" in raw
    assert "or `ISSUE #N` where `N` is a positive repository issue number" in raw
    assert "never record free-form incident details" in raw

    matches = list(re.finditer(r"^### Session (\d+)\s*$", raw, flags=re.MULTILINE))

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
        assert _INCIDENT_REFERENCE_RE.fullmatch(incident_summary), (
            f"Session {match.group(1)} incident summary must be exactly NONE "
            "or ISSUE #<positive integer>"
        )
