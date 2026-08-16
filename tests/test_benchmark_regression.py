from __future__ import annotations

import pytest

from scripts.evaluate_benchmark_regression import (
    derive_tolerance_percent,
    evaluate_regression,
)


def _study(*, median_value: float, p95_value: float, p99_value: float) -> dict[str, object]:
    metric = lambda value: {"median": value}  # noqa: E731
    return {
        "fixture": "fixed",
        "units": "microseconds",
        "environment": {"python": "3.14.7", "processor": "x86_64"},
        "workloads": {
            "workload": {
                "median_us": metric(median_value),
                "p95_us": metric(p95_value),
                "p99_us": metric(p99_value),
            }
        },
    }


def _noise(*, median_mad: float = 0.5, p95_mad: float = 1.0) -> dict[str, object]:
    return {
        "fixture": "fixed",
        "units": "microseconds",
        "workloads": {
            "workload": {
                "median_us": {"mad_percent": median_mad},
                "p95_us": {"mad_percent": p95_mad},
                "p99_us": {"mad_percent": 50.0},
            }
        },
    }


def test_derive_tolerance_uses_floor_and_noise_multiplier() -> None:
    assert derive_tolerance_percent(0.2) == 5.0
    assert derive_tolerance_percent(1.2) == pytest.approx(7.2)


def test_derive_tolerance_fails_closed_for_unstable_baseline() -> None:
    with pytest.raises(ValueError, match="too unstable"):
        derive_tolerance_percent(3.0)


def test_regression_gate_blocks_gated_metric_but_not_p99() -> None:
    reference = _study(median_value=100, p95_value=120, p99_value=150)
    candidate = _study(median_value=104, p95_value=130, p99_value=300)

    report = evaluate_regression(reference, candidate, _noise())

    assert report["decision"] == "FAIL"
    workload = report["workloads"]["workload"]
    assert workload["median_us"]["passed"] is True
    assert workload["p95_us"]["passed"] is False
    assert workload["p99_us"]["gated"] is False
    assert workload["p99_us"]["passed"] is None


def test_regression_gate_passes_improvements_and_preserves_human_review() -> None:
    report = evaluate_regression(
        _study(median_value=100, p95_value=120, p99_value=150),
        _study(median_value=95, p95_value=118, p99_value=140),
        _noise(),
    )

    assert report["decision"] == "PASS"
    assert report["human_release_review_required"] is True
    assert report["failures"] == []


def test_regression_gate_requires_same_runner_environment() -> None:
    reference = _study(median_value=100, p95_value=120, p99_value=150)
    candidate = _study(median_value=100, p95_value=120, p99_value=150)
    candidate["environment"] = {"python": "3.14.7", "processor": "arm64"}

    with pytest.raises(ValueError, match="environments differ"):
        evaluate_regression(reference, candidate, _noise())
