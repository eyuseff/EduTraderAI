import re
from pathlib import Path


LOG_PATH = Path("docs/operations/V41_RELEASE_OBSERVATION_LOG.md")


def test_numbered_v41_sessions_record_full_lowercase_commit_sha() -> None:
    raw = LOG_PATH.read_text(encoding="utf-8")
    matches = list(re.finditer(r"^### Session (\d+)\s*$", raw, flags=re.MULTILINE))

    for index, match in enumerate(matches):
        section_end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        section = raw[match.end() : section_end]
        observed_commit: str | None = None

        for line in section.splitlines():
            if not line.startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) == 2 and cells[0] == "Observed commit":
                observed_commit = cells[1].strip().strip("`")
                break

        assert observed_commit is not None
        assert re.fullmatch(r"[0-9a-f]{40}", observed_commit), (
            f"Session {match.group(1)} Observed commit must be a full lowercase "
            "40-character Git SHA"
        )
