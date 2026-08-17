from pathlib import Path


WORKFLOW_PATHS = (
    Path(".github/workflows/continuous-feature-validation.yml"),
    Path(".github/workflows/release-verification.yml"),
    Path(".github/workflows/benchmark-noise-study.yml"),
)

ACTION_PINS = {
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/setup-python": "5fda3b95a4ea91299a34e894583c3862153e4b97",
    "actions/upload-artifact": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
}


def _checkout_step_blocks(source: str) -> tuple[str, ...]:
    return tuple(
        block
        for block in source.split("      - name: ")
        if "uses: actions/checkout@" in block
    )


def _action_use_lines(source: str) -> tuple[str, ...]:
    return tuple(
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith("uses: actions/")
    )


def test_all_established_ci_checkouts_disable_token_persistence() -> None:
    for workflow_path in WORKFLOW_PATHS:
        source = workflow_path.read_text(encoding="utf-8")
        checkout_steps = _checkout_step_blocks(source)

        assert checkout_steps, f"no checkout step found in {workflow_path}"
        for checkout_step in checkout_steps:
            assert "persist-credentials: false" in checkout_step, (
                f"checkout token persistence remains enabled in {workflow_path}"
            )


def test_all_established_ci_actions_are_pinned_to_reviewed_commits() -> None:
    for workflow_path in WORKFLOW_PATHS:
        source = workflow_path.read_text(encoding="utf-8")
        action_lines = _action_use_lines(source)

        assert action_lines, f"no GitHub Actions uses found in {workflow_path}"
        for action_line in action_lines:
            action_ref = action_line.removeprefix("uses: ").split(" #", maxsplit=1)[0]
            action_name, action_pin = action_ref.split("@", maxsplit=1)
            assert action_name in ACTION_PINS, (
                f"unreviewed GitHub Action in {workflow_path}: {action_name}"
            )
            assert action_pin == ACTION_PINS[action_name], (
                f"unpinned or unexpected GitHub Action ref in {workflow_path}: "
                f"{action_ref}"
            )
