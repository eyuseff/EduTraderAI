"""Evaluate paired benchmark-noise studies using evidence-derived thresholds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

_GATED_METRICS = ("median_us", "p95_us")
_ADVISORY_METRICS = ("p99_us",)
_MIN_TOLERANCE_PERCENT = 5.0
_MAD_MULTIPLIER = 6.0
_MAX_TOLERANCE_PERCENT = 15.0


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _metric_center(study: dict[str, object], workload: str, metric: str) -> float:
    workloads = study["workloads"]
    if not isinstance(workloads, dict):
        raise ValueError("workloads must be an object")
    workload_payload = workloads[workload]
    if not isinstance(workload_payload, dict):
        raise ValueError("workload payload must be an object")
    metric_payload = workload_payload[metric]
    if not isinstance(metric_payload, dict):
        raise ValueError("metric payload must be an object")
    center = metric_payload["median"]
    if not isinstance(center, (int, float)) or isinstance(center, bool) or center <= 0:
        raise ValueError("metric median must be a positive number")
    return float(center)


def _noise_mad_percent(
    noise_baseline: dict[str, object], workload: str, metric: str
) -> float:
    workloads = noise_baseline["workloads"]
    if not isinstance(workloads, dict):
        raise ValueError("noise workloads must be an object")
    workload_payload = workloads[workload]
    if not isinstance(workload_payload, dict):
        raise ValueError("noise workload payload must be an object")
    metric_payload = workload_payload[metric]
    if not isinstance(metric_payload, dict):
        raise ValueError("noise metric payload must be an object")
    value = metric_payload["mad_percent"]
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise ValueError("noise MAD percent must be a non-negative number")
    return float(value)


def _workload_names(study: dict[str, object]) -> tuple[str, ...]:
    workloads = study["workloads"]
    if not isinstance(workloads, dict) or not workloads:
        raise ValueError("workloads must be a non-empty object")
    if any(not isinstance(name, str) for name in workloads):
        raise ValueError("workload names must be strings")
    return tuple(sorted(workloads))


def _validate_compatibility(
    reference: dict[str, object],
    candidate: dict[str, object],
    noise_baseline: dict[str, object],
) -> tuple[str, ...]:
    for key in ("fixture", "units"):
        if reference.get(key) != candidate.get(key):
            raise ValueError(f"paired benchmark {key} mismatch")
        if reference.get(key) != noise_baseline.get(key):
            raise ValueError(f"noise baseline {key} mismatch")
    if reference.get("environment") != candidate.get("environment"):
        raise ValueError("paired benchmark environments differ")
    reference_workloads = _workload_names(reference)
    if _workload_names(candidate) != reference_workloads:
        raise ValueError("paired benchmark workloads differ")
    if _workload_names(noise_baseline) != reference_workloads:
        raise ValueError("noise baseline workloads differ")
    return reference_workloads


def derive_tolerance_percent(mad_percent: float) -> float:
    """Derive one blocking tolerance from measured robust baseline noise."""

    tolerance = max(_MIN_TOLERANCE_PERCENT, _MAD_MULTIPLIER * mad_percent)
    if tolerance > _MAX_TOLERANCE_PERCENT:
        raise ValueError("noise baseline is too unstable for an automated gate")
    return round(tolerance, 3)


def _delta_percent(reference: float, candidate: float) -> float:
    if reference <= 0:
        raise ValueError("reference benchmark center must be positive")
    return round(((candidate - reference) / reference) * 100.0, 3)


def evaluate_regression(
    reference: dict[str, object],
    candidate: dict[str, object],
    noise_baseline: dict[str, object],
) -> dict[str, object]:
    """Compare paired studies; p99 remains diagnostic because its noise is high."""

    workloads = _validate_compatibility(reference, candidate, noise_baseline)
    evaluations: dict[str, object] = {}
    failures: list[str] = []

    for workload in workloads:
        metric_results: dict[str, object] = {}
        for metric in (*_GATED_METRICS, *_ADVISORY_METRICS):
            reference_center = _metric_center(reference, workload, metric)
            candidate_center = _metric_center(candidate, workload, metric)
            delta = _delta_percent(reference_center, candidate_center)
            gated = metric in _GATED_METRICS
            tolerance: float | None = None
            passed: bool | None = None
            if gated:
                tolerance = derive_tolerance_percent(
                    _noise_mad_percent(noise_baseline, workload, metric)
                )
                passed = delta <= tolerance
                if not passed:
                    failures.append(f"{workload}:{metric}")
            metric_results[metric] = {
                "reference_center_us": round(reference_center, 3),
                "candidate_center_us": round(candidate_center, 3),
                "delta_percent": delta,
                "gated": gated,
                "tolerance_percent": tolerance,
                "passed": passed,
            }
        evaluations[workload] = metric_results

    return {
        "schema_version": 1,
        "decision": "PASS" if not failures else "FAIL",
        "human_release_review_required": True,
        "method": {
            "paired_same_runner": True,
            "gated_metrics": list(_GATED_METRICS),
            "advisory_metrics": list(_ADVISORY_METRICS),
            "minimum_tolerance_percent": _MIN_TOLERANCE_PERCENT,
            "mad_multiplier": _MAD_MULTIPLIER,
            "maximum_tolerance_percent": _MAX_TOLERANCE_PERCENT,
        },
        "failures": failures,
        "workloads": evaluations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--noise-baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    try:
        report = evaluate_regression(
            _load_json(arguments.reference),
            _load_json(arguments.candidate),
            _load_json(arguments.noise_baseline),
        )
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"BENCHMARK REGRESSION GATE FAILED CLOSED: {error}", file=sys.stderr)
        return 2

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if report["decision"] != "PASS":
        print("BENCHMARK REGRESSION DETECTED", file=sys.stderr)
        return 1
    print("Benchmark regression gate passed; human release review remains required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
