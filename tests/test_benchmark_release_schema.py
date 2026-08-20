"""Schema tests for the deterministic release benchmark harness."""

from __future__ import annotations

from scripts.benchmark_release import benchmark, measure, percentile

EXPECTED_WORKLOADS = {
    "trade_planner",
    "preview_trade_service",
    "submit_trade_service_no_broker_delay",
    "execution_supervisor",
    "scanner_signal_to_decision",
}
EXPECTED_RESULT_FIELDS = {"iterations", "median_us", "p95_us", "p99_us"}


def test_measure_reports_expected_latency_schema_after_warmup() -> None:
    calls: list[int] = []
    operations = [lambda index=index: calls.append(index) for index in range(5)]

    result = measure(operations, warmup=2)

    assert set(result) == EXPECTED_RESULT_FIELDS
    assert result["iterations"] == 3
    assert result["median_us"] >= 0
    assert result["p95_us"] >= result["median_us"]
    assert result["p99_us"] >= result["p95_us"]
    assert calls == [0, 1, 2, 3, 4]


def test_percentile_selects_observed_sample_without_interpolation() -> None:
    samples = [10.0, 20.0, 30.0, 40.0, 50.0]

    assert percentile(samples, 0.0) == 10.0
    assert percentile(samples, 0.5) == 30.0
    assert percentile(samples, 0.95) == 50.0
    assert percentile(samples, 1.0) == 50.0


def test_benchmark_exposes_fixed_workloads_and_environment_metadata() -> None:
    report = benchmark(iterations=1, warmup=0)

    assert report["release"] == "4.1.0-rc1"
    assert report["units"] == "microseconds"
    assert "100k equity" in str(report["fixture"])
    environment = report["environment"]
    assert isinstance(environment, dict)
    assert set(environment) == {"python", "platform", "processor"}

    results = report["results"]
    assert isinstance(results, dict)
    assert set(results) == EXPECTED_WORKLOADS
    for workload in results.values():
        assert isinstance(workload, dict)
        assert set(workload) == EXPECTED_RESULT_FIELDS
        assert workload["iterations"] == 1
        assert workload["median_us"] >= 0
        assert workload["p95_us"] >= workload["median_us"]
        assert workload["p99_us"] >= workload["p95_us"]
