import re
from pathlib import Path


LOG_PATH = Path("docs/operations/V41_RELEASE_OBSERVATION_LOG.md")


def test_numbered_v41_sessions_require_redacted_blocking_status() -> None:
    raw = LOG_PATH.read_text(encoding="utf-8")
    assert "must record exactly `CLEAR`" in raw
    assert "or `BLOCKED` when any blocking flag is observed" in raw
    assert "never record raw flag names, raw flag values" in raw

    matches = list(re.finditer(r"^### Session (\d+)\s*$", raw, flags=re.MULTILINE))

    for index, match in enumerate(matches):
        section_end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        section = raw[match.end() : section_end]
        blocking_status: str | None = None

        for line in section.splitlines():
            if not line.startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) == 2 and cells[0] == "Blocking-flag status":
                blocking_status = cells[1].strip().strip("`")
                break

        assert blocking_status is not None
        assert blocking_status in {"CLEAR", "BLOCKED"}, (
            f"Session {match.group(1)} Blocking-flag status must be exactly "
            "CLEAR or BLOCKED"
        )
