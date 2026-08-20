"""Run the complete EduTraderAI v4.1 release-candidate verification gate."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import subprocess
import sys
from pathlib import Path

from generate_release_summary import write_release_summary
from package_release_evidence import build_evidence_pack
from release_identity import RELEASE_CANDIDATE

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
    "scripts/generate_release_summary.py",
    "scripts/package_release_evidence.py",
    "scripts/release_identity.py",
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
    try:
        subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    except subprocess.CalledProcessError:
        print(f"::error title=Release gate failed::{label}", flush=True)
        raise


def run_black_check() -> None:
    """Run Black and expose any would-reformat paths as CI annotations."""

    command = ("black", "--check", *SUPPORTED_PYTHON_TARGETS)
    print("\n==> Black formatting check", flush=True)
    print(" ".join(command), flush=True)
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout, end="", flush=True)
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr, flush=True)
    if result.returncode:
        details = [
            line.strip()
            for line in (result.stdout + result.stderr).splitlines()
            if "would reformat" in line
        ]
        for detail in details:
            print(
                f"::error title=Black formatting required::{detail}",
                flush=True,
            )
        print("::error title=Release gate failed::Black formatting check", flush=True)
        raise subprocess.CalledProcessError(result.returncode, command)


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


def source_commit_sha() -> str:
    """Resolve the exact commit being verified without mutating repository state."""

    result = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip().lower()
    if len(value) != 40 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError("unable to resolve a full source commit SHA")
    return value


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

    run_black_check()
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

    print("\n==> Release verification summary", flush=True)
    write_release_summary(
        PROJECT_ROOT / "build/verification.json",
        json_path=PROJECT_ROOT / "build/release_summary.json",
        markdown_path=PROJECT_ROOT / "build/release_summary.md",
        source_commit_sha=source_commit_sha(),
    )
    print(
        "Generated build/release_summary.json and build/release_summary.md",
        flush=True,
    )

    if coverage:
        print("\n==> Release evidence pack", flush=True)
        build_evidence_pack(
            PROJECT_ROOT,
            PROJECT_ROOT / "docs/releases/release-evidence-manifest-v4.1.json",
            PROJECT_ROOT / "build/release_evidence.zip",
        )
        print(
            "Generated verified build/release_evidence.zip and SHA-256 sidecar",
            flush=True,
        )

    print(f"\nEduTraderAI {RELEASE_CANDIDATE} verification passed.", flush=True)


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
    except (OSError, subprocess.CalledProcessError, ValueError, TypeError) as error:
        print(f"\nRELEASE VERIFICATION FAILED: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
