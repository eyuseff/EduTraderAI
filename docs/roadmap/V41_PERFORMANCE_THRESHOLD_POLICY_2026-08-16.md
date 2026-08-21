# V41-PF-002 Performance Regression Threshold Policy

## Status

Proposed automated performance gate backed by measured benchmark noise. The gate can block a regression, but it cannot approve a release. Human release review remains required.

## Evidence basis

The retained PF-002 noise baseline comes from GitHub Actions run `31962751728`, artifact `9267665882`, SHA-256 `cebf65ce113b7d76c8d635f5fe26e76d50eb9bd762a69157a8e8b4e7d114f501`, on Python 3.14.7 / Linux x86_64. It used seven repeated executions of the existing 300-iteration plus 30-warmup deterministic benchmark fixture.

Observed robust noise was low for medians and p95 centers. The largest median MAD was 0.736%. The largest p95 MAD was 1.464%. In contrast, p99 was materially noisier for some workloads: `execution_supervisor` had a 42.702% p99 range and `preview_trade_service` had a 40.846% p99 range.

Historical v4.0 operational notes also recorded ordinary median movement up to about +2.0% without a performance regression. The automated floor is therefore 5%, which is 2.5 times that documented routine movement and remains above every measured median MAD.

## Gate method

The CI gate compares the pull-request head with its exact base commit on the same GitHub runner. Before either side contributes recorded samples, candidate and exact base each execute an identical unmeasured three-repeat priming study using the same 300-iteration plus 30-warmup fixture. Those priming results are retained only as diagnostic evidence and are never supplied to the regression evaluator. Each side then executes the deterministic benchmark seven recorded times, and each workload/metric is represented by the median center across those seven recorded runs.

The symmetric priming step exists to prevent fixed candidate-first hosted-runner warm-up from being interpreted as a code regression. It does not widen any threshold, reduce the recorded sample count, or convert a failing comparison into a pass by ignoring measured evidence.

Blocking metrics:

- `median_us`
- `p95_us`

Advisory metric:

- `p99_us`

For each blocking workload/metric, tolerance is derived from the retained noise baseline:

`max(5.0%, 6 × baseline MAD percent)`

If the derived tolerance exceeds 15%, the baseline is considered too unstable for automated gating and the evaluator fails closed rather than silently widening the threshold.

With the retained baseline, median tolerances resolve to 5% for all five workloads. p95 tolerances are 5% except where the measured MAD requires a larger evidence-derived allowance; the largest is 8.784% for `trade_planner` p95.

A negative delta is an improvement and passes. A positive delta above the derived tolerance fails the performance gate. p99 is always reported but does not block until a future evidence set demonstrates stable enough tails.

## Noise controls

- Base and head must run on the same runner/environment in the same job.
- Fixture, units, and workload set must match exactly.
- Candidate and exact base each receive the same three-repeat unmeasured priming study immediately before their seven recorded runs.
- Priming output is preserved separately for diagnostics and cannot be used by the evaluator as candidate or reference evidence.
- Each side still contributes exactly seven recorded benchmark runs.
- The gate compares centers across recorded repeated runs rather than a single benchmark sample.
- The retained noise baseline is used only to derive tolerances, not as an absolute latency target.
- Environment or schema mismatch fails closed.

## Governance boundary

A green performance gate means only that no evidence-backed regression threshold was exceeded in this benchmark. It does not authorize a stable tag, deployment, broker action, live trading, Paper credential use, policy change, or release approval.

PF-002 can be considered implemented when the paired evaluator, tests, CI workflow, retained noise baseline, and sample regression report are all verified by the normal repository gates.
