import re
from pathlib import Path


LOG_PATH = Path("docs/operations/V41_RELEASE_OBSERVATION_LOG.md")
_SECRET_VALUE_MARKERS = (
    "sentinel_integration_secret_do_not_expose",
    "sentinel_broker_token_do_not_expose",
    "sentinel_password_do_not_expose",
    "api_key=",
    "secret=",
    "token=",
    "password=",
    "authorization:",
    "bearer ",
)


def test_numbered_v41_sessions_reject_secret_shaped_evidence() -> None:
    raw = LOG_PATH.read_text(encoding="utf-8")
    assert (
        "Credentials, account identifiers, broker order identifiers, raw broker "
        "payloads, and unredacted logs must never be committed or published."
    ) in " ".join(raw.split())

    matches = list(re.finditer(r"^### Session (\d+)\s*$", raw, flags=re.MULTILINE))

    for index, match in enumerate(matches):
        section_end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        section = raw[match.end() : section_end].lower()

        for marker in _SECRET_VALUE_MARKERS:
            assert marker not in section, (
                f"Session {match.group(1)} contains secret-shaped marker {marker!r}"
            )
