from pathlib import Path


WORKFLOW_PATH = Path(".github/workflows/continuous-feature-validation.yml")


def test_protected_path_diff_detection_fails_closed() -> None:
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    safety_step = source.split(
        "- name: Enforce protected-path safety boundary", maxsplit=1
    )[1].split("- name: Set up Python 3.14", maxsplit=1)[0]

    assert "fetch-depth: 0" in source
    assert "set -euo pipefail" in safety_step
    assert 'RANGE="${{ github.event.before }}...${{ github.sha }}"' in safety_step
    assert 'CHANGED="$(git diff --name-only "$RANGE")"' in safety_step
    assert 'git diff --name-only "$RANGE" || true' not in safety_step
