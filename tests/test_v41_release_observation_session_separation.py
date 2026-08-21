import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


LOG_PATH = Path("docs/operations/V41_RELEASE_OBSERVATION_LOG.md")
_MARKET_TZ = ZoneInfo("America/New_York")


def _parse_utc_timestamp(value: str) -> datetime:
    text = value.strip().strip("`")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None, f"timestamp must be timezone-aware: {value!r}"
    assert parsed.utcoffset() == timedelta(0), f"timestamp must be UTC: {value!r}"
    return parsed


def _market_date(value: str) -> object:
    return _parse_utc_timestamp(value).astimezone(_MARKET_TZ).date()


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


def test_numbered_v41_observation_sessions_use_distinct_market_dates() -> None:
    raw = LOG_PATH.read_text(encoding="utf-8")
    matches = list(re.finditer(r"^### Session (\d+)\s*$", raw, flags=re.MULTILINE))
    credited_market_dates: set[object] = set()

    for index, match in enumerate(matches):
        section_end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        section = raw[match.end() : section_end]
        start_value: str | None = None

        for line in section.splitlines():
            if not line.startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) == 2 and cells[0] == "Session start UTC":
                start_value = cells[1]
                break

        assert start_value is not None
        market_date = _market_date(start_value)
        assert market_date not in credited_market_dates, (
            f"Session {match.group(1)} shares a U.S. market date with an already credited session"
        )
        credited_market_dates.add(market_date)


def test_market_date_identity_uses_new_york_calendar_day() -> None:
    assert _market_date("2026-08-21T13:30:00Z") == _market_date("2026-08-21T19:59:00Z")
    assert _market_date("2026-08-21T13:30:00Z") != _market_date("2026-08-22T13:30:00Z")
