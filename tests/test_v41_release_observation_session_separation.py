import re
from datetime import datetime, timedelta
from pathlib import Path


LOG_PATH = Path("docs/operations/V41_RELEASE_OBSERVATION_LOG.md")


def _parse_utc_timestamp(value: str) -> datetime:
    text = value.strip().strip("`")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None, f"timestamp must be timezone-aware: {value!r}"
    assert parsed.utcoffset() == timedelta(0), f"timestamp must be UTC: {value!r}"
    return parsed


def test_numbered_v41_observation_sessions_do_not_overlap() -> None:
    raw = LOG_PATH.read_text(encoding="utf-8")
    matches = list(re.finditer(r"^### Session (\d+)\s*$", raw, flags=re.MULTILINE))
    previous_end: datetime | None = None

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
        if previous_end is not None:
            assert start >= previous_end, (
                f"Session {match.group(1)} must not overlap the preceding Paper-market session"
            )
        previous_end = end
