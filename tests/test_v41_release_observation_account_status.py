import re
from pathlib import Path


LOG_PATH = Path("docs/operations/V41_RELEASE_OBSERVATION_LOG.md")


def test_numbered_v41_sessions_require_redacted_account_status() -> None:
    raw = LOG_PATH.read_text(encoding="utf-8")
    assert "must record exactly `ACTIVE` or `INACTIVE`" in raw
    assert "account identifier cannot be embedded in this field" in raw

    matches = list(re.finditer(r"^### Session (\d+)\s*$", raw, flags=re.MULTILINE))

    for index, match in enumerate(matches):
        section_end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        section = raw[match.end() : section_end]
        account_status: str | None = None

        for line in section.splitlines():
            if not line.startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) == 2 and cells[0] == "Account-active status":
                account_status = cells[1].strip().strip("`")
                break

        assert account_status is not None
        assert account_status in {"ACTIVE", "INACTIVE"}, (
            f"Session {match.group(1)} Account-active status must be exactly "
            "ACTIVE or INACTIVE"
        )
