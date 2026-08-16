# EduTraderAI v4.1 Benchmark Definition

Date: 2026-08-16

Backlog item: V41-PF-001 — Define benchmark environment and workloads.

Status: Benchmark definition established from the existing deterministic `scripts/benchmark_release.py` harness.

## Purpose

Define a reproducible performance-measurement contract before formal regression thresholds are selected. This benchmark measures deterministic application/runtime overhead using synthetic in-process fixtures. It does **not** measure internet, exchange, broker API, disk/network filesystem, or external-service latency.

No broker credentials, network calls, `state/`, Live trading, or external order action are required or permitted by this benchmark definition.

## Existing harness

The authoritative starting harness is `scripts/benchmark_release.py`.

It uses:

- `perf_counter_ns()` monotonic timing;
- microseconds as the reporting unit;
- a separate warmup phase excluded from reported samples;
- median, p95 and p99 latency summaries;
- fixed deterministic market/account inputs;
- a zero-delay synthetic Paper broker implemented inside the benchmark script;
- no external broker/network dependency;
- JSON output including environment metadata and workload results.

## Benchmark fixture

Unless a future benchmark-version change explicitly says otherwise, the canonical fixture is:

| Field | Value |
|---|---|
| Equity | 100,000 |
| Cash | 100,000 |
| Buying power | 100,000 |
| Broker mode | Synthetic Paper / zero external delay |
| Symbol | AAPL |
| Side | BUY |
| Entry | 100 |
| Stop | 97.5 |
| Target | 105 |
| Scanner universe | AAPL only |
| Scanner qualified signal score | 95 |
| Average volume fixture | 2,000,000 |
| Daily change fixture | 1.0% |
| Audit sink for scanner workload | No-op in-process audit |
| Operational event destination | Null/in-process where used |

The fixture deliberately removes I/O and broker latency so changes in application code are easier to compare.

## Workloads

The benchmark result must contain exactly these baseline workload identities unless the benchmark schema/version is deliberately revised:

### PF-WL-001 — `trade_planner`

Measures deterministic planning/sizing/risk policy evaluation for the fixed AAPL intent and portfolio view.

Primary purpose: detect regression in the deterministic planning core.

### PF-WL-002 — `preview_trade_service`

Measures the application preview service around the same deterministic planner and portfolio state.

Primary purpose: detect application-service overhead beyond direct planning.

### PF-WL-003 — `submit_trade_service_no_broker_delay`

Measures submission-service work using a newly prepared deterministic request and a synthetic zero-delay Paper broker.

Primary purpose: measure submission orchestration without network/broker latency.

Important: this is **not** a broker-service latency benchmark.

### PF-WL-004 — `execution_supervisor`

Measures supervised execution orchestration with distinct idempotency/correlation identities and the same synthetic zero-delay Paper path.

Primary purpose: detect overhead regressions in supervisor admission/policy/orchestration.

### PF-WL-005 — `scanner_signal_to_decision`

Measures one deterministic scanner signal-to-decision cycle with scanner market discovery replaced by the fixed in-process fixture.

Primary purpose: capture the higher-level orchestration path from deterministic signal input to supervised decision.

## Sample protocol

The default benchmark protocol is:

- measured iterations: **300**;
- warmup iterations: **30**;
- total operation constructions/executions per workload: 330;
- warmup samples are discarded from statistics;
- CLI must reject fewer than 20 measured iterations;
- warmup cannot be negative.

For investigative local runs, iteration count may be changed, but any evidence used to define or evaluate release thresholds must report the exact iteration/warmup values and should use the canonical protocol unless the comparison explicitly justifies another protocol.

## Required per-workload result schema

Each workload result must report:

- `iterations`: integer sample count after warmup;
- `median_us`: non-negative numeric median latency in microseconds;
- `p95_us`: non-negative numeric p95 latency in microseconds;
- `p99_us`: non-negative numeric p99 latency in microseconds.

Required relationships:

- `iterations > 0`;
- `median_us >= 0`;
- `p95_us >= median_us` for a normal percentile calculation over the same sample set;
- `p99_us >= p95_us` for a normal percentile calculation over the same sample set.

The current percentile implementation selects from the sorted observed samples; it does not interpolate synthetic values.

## Required top-level evidence

A benchmark evidence document/output should retain at least:

- benchmark/schema version or release identifier;
- unit (`microseconds`);
- fixture description;
- Python version;
- operating-system/platform string;
- processor description when reported;
- measured-iteration count;
- warmup count;
- all required workload results;
- source commit SHA when captured by a future evidence wrapper.

The current script already reports release, units, fixture, Python/platform/processor and workload results. PF-002/RA work may extend evidence metadata without changing benchmark semantics.

## Environment control

Performance evidence is comparable only when important environment differences are visible. At minimum record Python version, platform and processor. Formal PF-002 threshold evidence should additionally control or report, where available:

- CI runner class or machine identifier/category;
- CPU architecture/count;
- power/performance mode if locally relevant;
- container/virtualization context;
- competing workload assumptions;
- source commit;
- benchmark script version/hash.

A threshold must not combine materially different runner populations without an explicit normalization/noise policy.

## Noise handling principles for PF-002

PF-001 deliberately does not select numerical pass/fail thresholds. PF-002 must derive thresholds from repeated baseline observations on the intended execution environment rather than inventing percentages.

The following principles are fixed now:

1. Median and tail metrics must be evaluated separately.
2. A single fastest sample is never the baseline.
3. Warmup is excluded.
4. Formal thresholds require repeated historical/current runs on comparable environments.
5. Threshold failure must identify workload and metric.
6. An environment mismatch can make the comparison `INCOMPARABLE` rather than falsely passing/failing.

## Exclusions

The benchmark does not measure:

- real Alpaca/Paper/Live API latency;
- DNS/TLS/network latency;
- market-data retrieval latency;
- exchange fill/acknowledgment timing;
- durable SQLite execution-persistence throughput unless a future workload explicitly adds it;
- external event publisher latency;
- filesystem/network-storage performance;
- end-user UI latency.

Those require separate workload definitions and must never be silently mixed into these deterministic baselines.

## Reproducibility command

Canonical local invocation:

```bash
python scripts/benchmark_release.py --iterations 300 --warmup 30
```

This command is a deterministic synthetic benchmark and requires no broker credentials or external endpoint.

## V41-PF-001 acceptance mapping

- Environment documented: yes, including minimum metadata and comparability rules.
- Fixtures documented: yes, fixed account/AAPL/scanner/zero-delay Paper fixture.
- Workloads representative: five existing release benchmark paths are described with intent and exclusions.
- Warmup/iteration protocol documented: yes.
- Median/tail metrics documented: median/p95/p99.
- Benchmark schema requirements documented: yes.
- Formal thresholds selected: intentionally no; this belongs to V41-PF-002 and requires baseline evidence.

## Handoff to V41-PF-002

Collect repeated baseline reports on the exact intended runner/environment, validate stability/noise, then define an evidence-based threshold evaluator. Do not choose regression percentages from intuition alone.