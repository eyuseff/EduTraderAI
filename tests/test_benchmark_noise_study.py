from __future__ import annotations

import pytest

from scripts.benchmark_noise_study import run_noise_study, summarize_runs


def _run(value: float) -> dict[str, object]:
    result = {
        "iterations": 300,
        "median_us": value,
        "p95_us": value * 2,
        "p99_us": value * 3,
    }
    return {
        "release": "4.0.0-rc1",
        "units": "microseconds",
        "fixture": "fixed",
        "environment": {
            "python": "3.14.0",
            "platform": "test",
            "processor": "test",
        },
        "results": {"workload": result},
    }


def test_summarize_runs_reports_robust_noise_statistics() -> None:
    summary = summarize_runs([_run(10), _run(11), _run(12)])

    assert summary["threshold_decision"] == "NOT_SELECTED"
    workload = summary["workloads"]["workload"]
    median_metric = workload["median_us"]
    assert median_metric["values"] == [10.0, 11.0, 12.0]
    assert median_metric["median"] == 11.0
    assert median_metric["mad"] == 1.0
    assert median_metric["mad_percent"] == pytest.approx(9.091)
    assert median_metric["max_abs_deviation_percent"] == pytest.approx(9.091)
    assert median_metric["range_percent"] == pytest.approx(18.182)


def test_summarize_runs_rejects_environment_drift() -> None:
    runs = [_run(10), _run(11), _run(12)]
    runs[2]["environment"] = {"python": "3.15", "platform": "test"}

    with pytest.raises(ValueError, match="environments differ"):
        summarize_runs(runs)


def test_summarize_runs_requires_multiple_samples() -> None:
    with pytest.raises(ValueError, match="at least three"):
        summarize_runs([_run(10), _run(11)])


def test_run_noise_study_primes_once_without_recording_the_prime() -> None:
    calls: list[tuple[int, int]] = []

    def runner(iterations: int, warmup: int) -> dict[str, object]:
        calls.append((iterations, warmup))
        return _run(float(len(calls)))

    summary = run_noise_study(
        repeats=3,
        iterations=300,
        warmup=30,
        runner=runner,
    )

    assert calls == [(300, 30)] * 4
    assert summary["run_count"] == 3
    assert summary["workloads"]["workload"]["median_us"]["values"] == [2.0, 3.0, 4.0]
