import re
from pathlib import Path


LOG_PATH = Path("docs/operations/V41_RELEASE_OBSERVATION_LOG.md")


def test_numbered_v41_sessions_require_paper_environment() -> None:
    raw = LOG_PATH.read_text(encoding="utf-8")
    assert "every counted session must record exactly `PAPER`" in raw

    matches = list(re.finditer(r"^### Session (\d+)\s*$", raw, flags=re.MULTILINE))

    for index, match in enumerate(matches):
        section_end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        section = raw[match.end() : section_end]
        environment: str | None = None

        for line in section.splitlines():
            if not line.startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) == 2 and cells[0] == "Environment":
                environment = cells[1].strip().strip("`")
                break

        assert environment is not None
        assert environment == "PAPER", (
            f"Session {match.group(1)} Environment must be exactly PAPER"
        )
