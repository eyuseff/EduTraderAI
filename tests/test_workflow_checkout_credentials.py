from pathlib import Path


WORKFLOW_PATHS = (
    Path(".github/workflows/continuous-feature-validation.yml"),
    Path(".github/workflows/release-verification.yml"),
    Path(".github/workflows/benchmark-noise-study.yml"),
)


def _checkout_step_blocks(source: str) -> tuple[str, ...]:
    return tuple(
        block
        for block in source.split("      - name: ")
        if "uses: actions/checkout@v7" in block
    )


def test_all_established_ci_checkouts_disable_credential_persistence() -> None:
    for workflow_path in WORKFLOW_PATHS:
        source = workflow_path.read_text(encoding="utf-8")
        checkout_steps = _checkout_step_blocks(source)

        assert checkout_steps, f"no checkout step found in {workflow_path}"
        for checkout_step in checkout_steps:
            assert "persist-credentials: false" in checkout_step, (
                f"checkout credentials remain persisted in {workflow_path}"
            )
