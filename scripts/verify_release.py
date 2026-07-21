"""Run the complete EduTraderAI v4.0 release-candidate verification gate."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SUPPORTED_PYTHON_TARGETS = (
    "app.py",
    "adapters",
    "engine/supervised_brain.py",
    "volcanoes/application/services",
    "volcanoes/application/supervisor",
    "volcanoes/application/platform",
    "volcanoes/application/operations",
    "volcanoes/events",
    "volcanoes/execution/broker.py",
    "volcanoes/execution/execution_pipeline.py",
    "volcanoes/execution/order_builder.py",
    "volcanoes/execution/trade_planner.py",
    "volcanoes/risk",
    "volcanoes/sizing",
    "tests/test_architecture_dependencies.py",
    "tests/test_platform_configuration.py",
    "tests/test_operational_metrics.py",
    "tests/test_v4_release_acceptance.py",
    "scripts/benchmark_release.py",
    "scripts/verify_release.py",
)

MYPY_TARGETS = (
    "adapters",
    "engine/supervised_brain.py",
    "volcanoes/application/services",
    "volcanoes/application/supervisor",
    "volcanoes/application/platform",
    "volcanoes/application/operations",
    "volcanoes/events",
    "volcanoes/execution/execution_pipeline.py",
    "volcanoes/execution/trade_planner.py",
    "volcanoes/risk",
    "volcanoes/sizing",
)


def run_step(label: str, command: tuple[str, ...]) -> None:
    """Run one release gate and stop immediately on failure."""

    print(f"\n==> {label}", flush=True)
    print(" ".join(command), flush=True)
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def collect_test_count() -> int:
    """Count collected tests for the sanitized verification artifact."""

    result = subprocess.run(
        (sys.executable, "-m", "pytest", "--collect-only", "-q"),
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return sum("::" in line for line in result.stdout.splitlines())


def write_verification_metadata(*, test_count: int, coverage: bool) -> None:
    """Write ignored, secret-free metadata after every gate succeeds."""

    payload: dict[str, object] = {
        "status": "PASS",
        "command": "make verify",
        "test_count": test_count,
        "line_coverage_percent": None,
        "branch_coverage_percent": None,
        "combined_coverage_percent": None,
        "verified_at": datetime.now(UTC).isoformat(),
    }
    if coverage:
        coverage_payload = json.loads(
            (PROJECT_ROOT / "build/coverage.json").read_text(encoding="utf-8")
        )
        totals = coverage_payload["totals"]
        payload.update(
            {
                "line_coverage_percent": round(
                    float(totals["percent_statements_covered"]), 1
                ),
                "branch_coverage_percent": round(
                    float(totals["percent_branches_covered"]), 1
                ),
                "combined_coverage_percent": round(float(totals["percent_covered"]), 1),
            }
        )
    (PROJECT_ROOT / "build").mkdir(exist_ok=True)
    (PROJECT_ROOT / "build/verification.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def verify(*, coverage: bool) -> None:
    """Execute all supported release-candidate gates."""

    run_step("Black formatting check", ("black", "--check", *SUPPORTED_PYTHON_TARGETS))
    run_step("Ruff static analysis", ("ruff", "check", *SUPPORTED_PYTHON_TARGETS))
    run_step(
        "MyPy deterministic boundary",
        (
            "mypy",
            "--follow-imports=skip",
            "--ignore-missing-imports",
            *MYPY_TARGETS,
        ),
    )
    run_step(
        "Architecture dependency tests",
        (
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_architecture_dependencies.py",
        ),
    )
    run_step(
        "Import and bytecode smoke tests",
        (
            sys.executable,
            "-c",
            (
                "import adapters.paper_order_preview; "
                "import adapters.paper_order_submission; "
                "import adapters.scanner_execution; "
                "import engine.supervised_brain; "
                "import volcanoes.application.platform; "
                "import volcanoes.application.operations; "
                "import volcanoes.application.services; "
                "import volcanoes.application.supervisor; "
                "import volcanoes.events"
            ),
        ),
    )
    run_step(
        "Streamlit entry-point compilation",
        (sys.executable, "-m", "py_compile", "app.py"),
    )
    run_step("Full pytest suite", (sys.executable, "-m", "pytest", "-q"))

    if coverage:
        run_step("Coverage data reset", (sys.executable, "-m", "coverage", "erase"))
        run_step(
            "Branch coverage test run",
            (sys.executable, "-m", "coverage", "run", "-m", "pytest", "-q"),
        )
        run_step(
            "Coverage baseline enforcement",
            (sys.executable, "-m", "coverage", "report"),
        )
        (PROJECT_ROOT / "build").mkdir(exist_ok=True)
        run_step(
            "Coverage JSON artifact",
            (
                sys.executable,
                "-m",
                "coverage",
                "json",
                "-o",
                "build/coverage.json",
            ),
        )

    print("\n==> Verification metadata", flush=True)
    test_count = collect_test_count()
    write_verification_metadata(test_count=test_count, coverage=coverage)
    print(f"Collected test count: {test_count}", flush=True)

    print("\nEduTraderAI v4.0.0-rc1 verification passed.", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Run and enforce the documented coverage baseline.",
    )
    arguments = parser.parse_args()
    try:
        verify(coverage=arguments.coverage)
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"\nRELEASE VERIFICATION FAILED: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
