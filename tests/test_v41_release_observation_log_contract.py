from pathlib import Path


README_PATH = Path("README.md")
PLAN_PATH = Path("docs/operations/V41_STABLE_PROMOTION_PLAN.md")
LOG_PATH = Path("docs/operations/V41_RELEASE_OBSERVATION_LOG.md")


def _table_rows(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 2 or cells[0] in {"Item", "---"}:
            continue
        rows[cells[0]] = cells[1]
    return rows


def _normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def test_v41_observation_log_release_identity_matches_promotion_plan() -> None:
    plan_rows = _table_rows(PLAN_PATH)
    log_rows = _table_rows(LOG_PATH)

    for key in (
        "Release candidate",
        "RC commit",
        "RC published UTC",
        "Minimum elapsed observation",
        "Minimum separate Paper-market sessions",
        "Earliest Stable review",
    ):
        assert log_rows[key] == plan_rows[key]


def test_v41_observation_log_remains_fail_closed_about_session_credit() -> None:
    source = _normalized(LOG_PATH)

    assert (
        "No post-RC Paper-market session is credited merely because CI, repository "
        "checks, or the pre-RC Connected Alpaca Paper qualification passed."
    ) in source
    assert "A session does not require an order" in source
    assert (
        "no order may be submitted, replaced, or cancelled merely to satisfy the "
        "observation quota"
    ) in source
    assert "Do not infer broker-side observations from repository or CI state." in source
    assert (
        "Credentials, account identifiers, broker order identifiers, raw broker "
        "payloads, and unredacted logs must never be committed or published."
    ) in source


def test_repository_entrypoint_distinguishes_v41_log_from_v40_history() -> None:
    source = _normalized(README_PATH)

    assert (
        "[v4.1 release observation log]"
        "(docs/operations/V41_RELEASE_OBSERVATION_LOG.md)"
    ) in source
    assert (
        "historical [v4.0 observation log]"
        "(docs/operations/RELEASE_OBSERVATION_LOG.md)"
    ) in source
    assert "does not count toward the v4.1 Stable gate" in source
