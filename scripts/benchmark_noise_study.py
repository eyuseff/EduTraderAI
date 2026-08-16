"""Measure repeated-run noise for the deterministic release benchmark."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
import sys
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.benchmark_release import benchmark

_METRICS = ("median_us", "p95_us", "p99_us")


def _relative_percent(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        raise ValueError("benchmark metric denominator must be positive")
    return round((numerator / denominator) * 100.0, 3)


def summarize_runs(runs: list[dict[str, object]]) -> dict[str, object]:
    """Summarize repeated benchmark outputs without inventing thresholds."""

    if len(runs) < 3:
        raise ValueError("at least three benchmark runs are required")

    first = runs[0]
    expected_environment = first["environment"]
    expected_fixture = first["fixture"]
    expected_units = first["units"]
    expected_workloads = tuple(sorted(first["results"]))

    for run in runs[1:]:
        if run["environment"] != expected_environment:
            raise ValueError("benchmark environments differ across runs")
        if run["fixture"] != expected_fixture or run["units"] != expected_units:
            raise ValueError("benchmark fixture or units changed across runs")
        if tuple(sorted(run["results"])) != expected_workloads:
            raise ValueError("benchmark workloads differ across runs")

    workloads: dict[str, object] = {}
    for workload in expected_workloads:
        metric_summary: dict[str, object] = {}
        for metric in _METRICS:
            values = [float(run["results"][workload][metric]) for run in runs]
            center = median(values)
            absolute_deviations = [abs(value - center) for value in values]
            mad = median(absolute_deviations)
            max_abs_deviation = max(absolute_deviations)
            value_range = max(values) - min(values)
            metric_summary[metric] = {
                "values": [round(value, 3) for value in values],
                "median": round(center, 3),
                "min": round(min(values), 3),
                "max": round(max(values), 3),
                "mad": round(mad, 3),
                "mad_percent": _relative_percent(mad, center),
                "max_abs_deviation_percent": _relative_percent(
                    max_abs_deviation, center
                ),
                "range_percent": _relative_percent(value_range, center),
            }
        workloads[workload] = metric_summary

    return {
        "schema_version": 1,
        "purpose": "PF-002 benchmark noise characterization",
        "threshold_decision": "NOT_SELECTED",
        "run_count": len(runs),
        "environment": expected_environment,
        "fixture": expected_fixture,
        "units": expected_units,
        "workloads": workloads,
    }


def run_noise_study(
    *,
    repeats: int,
    iterations: int,
    warmup: int,
    runner: Callable[[int, int], dict[str, object]] = benchmark,
) -> dict[str, object]:
    if repeats < 3:
        raise ValueError("repeats must be at least three")
    return summarize_runs([runner(iterations, warmup) for _ in range(repeats)])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--iterations", type=int, default=300)
    parser.add_argument("--warmup", type=int, default=30)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()

    try:
        result = run_noise_study(
            repeats=arguments.repeats,
            iterations=arguments.iterations,
            warmup=arguments.warmup,
        )
    except (KeyError, TypeError, ValueError) as error:
        print(f"BENCHMARK NOISE STUDY FAILED: {error}", file=sys.stderr)
        return 1

    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        print(rendered, end="")
    else:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
