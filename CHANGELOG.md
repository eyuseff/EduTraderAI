# Changelog

All notable changes to EduTraderAI are documented in this file.

## [4.0.0-rc1] - 2026-07-20

### Added

- Deterministic `TradePlanner` and immutable `TradePlan` shared by preview and
  submission.
- Explicit immutable trading policies with buy-trade parity against the legacy
  paper preview configuration.
- Broker snapshot and execution adapters that keep concrete broker types outside
  Volcanoes.
- Presentation-neutral preview and submission application services.
- Immutable operational events, correlation IDs, and the `EventPublisher` port.
- `ExecutionSupervisor` with idempotency, cooldown, duplicate-execution, and
  same-symbol serialization policies.
- Supervised scanner preview and paper-submission workflows.
- Fail-closed startup configuration validation and immutable platform health
  diagnostics.
- End-to-end v4 acceptance tests, coverage and performance baselines, and the
  unified `make verify` release gate.
- Fixed-cardinality, process-local operational counters and monotonic latency
  summaries with immutable snapshots and fail-open instrumentation.
- Development-only operational dashboard and manual sanitized validation export.
- RC observation plan, runbook, incident template, validation log, and
  operational-validation ADR.
- GitHub Actions release verification using the unchanged local `make verify`
  gate and uploaded coverage metadata.

### Changed

- Manual Paper Order preview and submission default to the deterministic stack.
- Automated scanner execution defaults to `ExecutionSupervisor`.
- Streamlit reports version `4.0.0-rc1` and uses current dataframe width APIs.
- Scanner, manual order, and broker integrations now point inward through
  application services and deterministic core ports.

### Compatibility and rollback

- `USE_DETERMINISTIC_PREVIEW` and `USE_DETERMINISTIC_SUBMISSION` retain the
  legacy manual path when both are set to `False`.
- `USE_DETERMINISTIC_SCANNER` retains the legacy `EduTraderBrain` path when set
  to `False`.
- Mixed manual generations are rejected at startup to prevent preview/submission
  drift.

### Known limitations

- Operational events are not durable.
- Supervisor idempotency, cooldown state, and symbol locks are process-local.
- Broker snapshots have no transactional version.
- Execution remains paper-only and long-only.
- The supervisor market-state policy has no authoritative market adapter.
- Operational metrics reset on process restart; the stable release must
  disposition process-local coordination and `NullEventPublisher` explicitly.
