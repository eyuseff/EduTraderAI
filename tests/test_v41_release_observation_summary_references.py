import re
from pathlib import Path


LOG_PATH = Path("docs/operations/V41_RELEASE_OBSERVATION_LOG.md")
_REFERENCE_ONLY_RE = re.compile(r"(?:OBSERVED|ISSUE #[1-9][0-9]*)\Z")
_FIELDS = ("Application observations", "Broker observations")


def test_numbered_v41_sessions_require_reference_only_observation_summaries() -> None:
    raw = LOG_PATH.read_text(encoding="utf-8")

    for field in _FIELDS:
        assert f"The `{field}` field is fail-closed and reference-only" in raw

    assert "must record exactly `OBSERVED`" in raw
    assert "or `ISSUE #N` where `N` is a positive repository issue number" in raw
    assert "Recording this field does not require or authorize an order." in raw

    matches = list(re.finditer(r"^### Session (\d+)\s*$", raw, flags=re.MULTILINE))

    for index, match in enumerate(matches):
        section_end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        section = raw[match.end() : section_end]
        values: dict[str, str] = {}

        for line in section.splitlines():
            if not line.startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) == 2 and cells[0] in _FIELDS:
                values[cells[0]] = cells[1].strip().strip("`")

        for field in _FIELDS:
            assert field in values
            assert _REFERENCE_ONLY_RE.fullmatch(values[field]), (
                f"Session {match.group(1)} {field} must be exactly OBSERVED "
                "or ISSUE #<positive integer>"
            )
