import re
import subprocess
from pathlib import Path


LOG_PATH = Path("docs/operations/V41_RELEASE_OBSERVATION_LOG.md")
RC_COMMIT = "3296e319cafacd89ad703ca49b298b953b51223d"
_COMMIT_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")


def _git_succeeds(*args: str) -> bool:
    return (
        subprocess.run(
            ["git", *args],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def _git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def _is_countable_observed_commit(value: str) -> bool:
    if not _COMMIT_SHA_RE.fullmatch(value):
        return False
    if not _git_succeeds("cat-file", "-e", f"{value}^{{commit}}"):
        return False
    if not _git_succeeds("merge-base", "--is-ancestor", RC_COMMIT, value):
        return False
    return _git_succeeds("merge-base", "--is-ancestor", value, "HEAD")


def test_v41_observation_commit_lineage_guard_is_fail_closed() -> None:
    head = _git_output("rev-parse", "HEAD")
    pre_rc_parent = _git_output("rev-parse", f"{RC_COMMIT}^")

    assert _is_countable_observed_commit(RC_COMMIT)
    assert _is_countable_observed_commit(head)
    assert not _is_countable_observed_commit(pre_rc_parent)
    assert not _is_countable_observed_commit("0" * 40)
    assert not _is_countable_observed_commit("main")


def test_numbered_v41_sessions_record_observation_lineage_commit() -> None:
    raw = LOG_PATH.read_text(encoding="utf-8")
    assert "The `Observed commit` field is fail-closed and lineage-bound" in raw
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
        assert _is_countable_observed_commit(observed_commit), (
            f"Session {match.group(1)} Observed commit must be a full lowercase "
            "40-character repository commit on the RC-to-current-HEAD lineage"
        )
