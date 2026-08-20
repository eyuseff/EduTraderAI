from pathlib import Path


PLAN_PATH = Path("docs/operations/V41_STABLE_PROMOTION_PLAN.md")


def _plan() -> str:
    return " ".join(PLAN_PATH.read_text(encoding="utf-8").split())


def test_stable_promotion_observation_window_remains_fail_closed() -> None:
    source = _plan()

    assert "Release candidate | `v4.1.0-rc1`" in source
    assert "RC commit | `3296e319cafacd89ad703ca49b298b953b51223d`" in source
    assert "RC published UTC | `2026-08-20T17:20:13Z`" in source
    assert "Minimum elapsed observation | Seven calendar days" in source
    assert "Minimum separate Paper-market sessions | Five" in source
    assert "Earliest Stable review | `2026-08-27T17:20:13Z`" in source
    assert (
        "does not count as one of the five post-RC observation sessions" in source
    )
    assert "CI runs and repository-only checks also do not count" in source


def test_stable_promotion_does_not_incentivize_extra_orders() -> None:
    source = _plan()

    assert "A session does not need an order." in source
    assert (
        "No additional order may be submitted, replaced, or cancelled merely to "
        "satisfy an observation quota."
    ) in source


def test_stable_readiness_monitor_remains_repository_only() -> None:
    source = _plan()

    assert (
        "daily readiness monitor may perform only repository and GitHub read-only "
        "checks"
    ) in source
    assert (
        "The monitor must not use broker credentials, contact a broker, access "
        "protected runtime data, mutate repository files, create tags/releases, "
        "or deploy."
    ) in source


def test_stable_promotion_requires_exact_head_and_human_acceptance() -> None:
    source = _plan()

    assert "seven calendar days have elapsed since RC publication" in source
    assert "five separate post-RC Paper-market sessions are documented" in source
    assert (
        "`make verify` and the protected performance regression gate pass on the exact "
        "proposed Stable commit"
    ) in source
    assert "a final v4.1 GO/NO-GO review is recorded" in source
    assert (
        "the operator explicitly accepts the final review and Paper-only restrictions"
        in source
    )
    assert (
        "Stable tag and GitHub Release creation remain separate consequential "
        "publication actions."
    ) in source
