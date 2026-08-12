# EduTraderAI v4.1 Backlog
| Field | Value |
|---|---|
| Status | Initial planned backlog |
| Baseline | `v4.0.0` |
| Owner | NOT ASSIGNED |
| Target milestone | NOT DEFINED |

## V41-PQ-001 - Design Paper qualification state machine

| Field | Value |
|---|---|
| Priority | P0 |
| Status | PLANNED |
| Owner | NOT ASSIGNED |
| Target milestone | NOT DEFINED |

Rationale: Define the deterministic qualification lifecycle before implementation.

Scope: State machine, PASS/FAIL/BLOCKED outcomes, operator confirmation, cleanup states.

Out of scope: Broker implementation changes and live endpoint behavior.

Dependencies: Workstream A, existing Alpaca Paper adapter.

Acceptance criteria:

- State diagram documented
- Terminal states defined
- Failure handling documented

Test requirements:

- State transition unit tests
- Blocked/fail/pass mapping tests

Evidence requirements:

- Design document or ADR reference

## V41-PQ-002 - Enforce Paper-only endpoint and broker

| Field | Value |
|---|---|
| Priority | P0 |
| Status | PLANNED |
| Owner | NOT ASSIGNED |
| Target milestone | NOT DEFINED |

Rationale: Prevent qualification from reaching a live endpoint.

Scope: Paper broker detection, endpoint verification, fail-closed behavior.

Out of scope: Live trading support.

Dependencies: Broker configuration and startup validation.

Acceptance criteria:

- Live endpoint is blocked
- Paper endpoint is required
- Failure is explicit

Test requirements:

- Endpoint guard tests
- configuration failure tests

Evidence requirements:

- Redacted endpoint verification evidence

## V41-PQ-003 - Enforce deterministic one-share quantity

| Field | Value |
|---|---|
| Priority | P0 |
| Status | PLANNED |
| Owner | NOT ASSIGNED |
| Target milestone | NOT DEFINED |

Rationale: Close the v4.0 smoke-test limitation.

Scope: Qualification contract forces exactly one share while preserving policy checks.

Out of scope: General sizing policy changes.

Dependencies: Workstream A state machine.

Acceptance criteria:

- Quantity is exactly 1
- No larger order can be submitted from qualification mode

Test requirements:

- One-share enforcement tests
- attempted override tests

Evidence requirements:

- Qualification evidence showing quantity 1

## V41-PQ-004 - Generate safe non-marketable limit

| Field | Value |
|---|---|
| Priority | P0 |
| Status | PLANNED |
| Owner | NOT ASSIGNED |
| Target milestone | NOT DEFINED |

Rationale: Reduce fill risk during qualification.

Scope: Deterministic non-marketable limit selection and explanation.

Out of scope: New trading strategy logic.

Dependencies: Market quote or operator-provided reference price.

Acceptance criteria:

- Limit is non-marketable by rule
- Rationale is recorded

Test requirements:

- Price construction tests
- fill-risk guard tests

Evidence requirements:

- Evidence showing non-marketable order parameters

## V41-PQ-005 - Implement acknowledgment/status/cancel lifecycle

| Field | Value |
|---|---|
| Priority | P0 |
| Status | PLANNED |
| Owner | NOT ASSIGNED |
| Target milestone | NOT DEFINED |

Rationale: Make broker smoke qualification self-contained.

Scope: Submit, acknowledge, retrieve status, verify zero fill, cancel, confirm cleanup.

Out of scope: Manual broker cleanup as required success path.

Dependencies: Workstream A guards.

Acceptance criteria:

- Exactly one order submitted
- Status retrieved
- Order cancelled
- No open orders or position remain

Test requirements:

- Fake broker lifecycle tests
- exception mapping tests
- cleanup tests

Evidence requirements:

- Redacted lifecycle JSON

## V41-PQ-006 - Implement duplicate-execution prevention

| Field | Value |
|---|---|
| Priority | P0 |
| Status | PLANNED |
| Owner | NOT ASSIGNED |
| Target milestone | NOT DEFINED |

Rationale: Prevent repeated qualification orders.

Scope: Idempotency key, replay behavior, and duplicate blocking.

Out of scope: Distributed lock implementation unless selected later.

Dependencies: Workstream A and current supervisor patterns.

Acceptance criteria:

- Identical request cannot submit twice
- Replay result is explicit

Test requirements:

- Duplicate qualification tests
- idempotent replay tests

Evidence requirements:

- Evidence of duplicate prevention

## V41-PQ-007 - Generate redacted immutable evidence

| Field | Value |
|---|---|
| Priority | P0 |
| Status | PLANNED |
| Owner | NOT ASSIGNED |
| Target milestone | NOT DEFINED |

Rationale: Make qualification auditable without secrets.

Scope: JSON artifact, schema version, hash, manifest integration.

Out of scope: Storing credentials or full account identifiers.

Dependencies: Evidence manifest and release docs.

Acceptance criteria:

- Artifact is redacted
- SHA-256 generated
- Manifest can verify it

Test requirements:

- JSON schema tests
- redaction tests
- manifest tests

Evidence requirements:

- Immutable JSON and manifest row

## V41-CC-001 - Inventory current process-local coordination

| Field | Value |
|---|---|
| Priority | P1 |
| Status | PLANNED |
| Owner | NOT ASSIGNED |
| Target milestone | NOT DEFINED |

Rationale: Document the current deployment constraint accurately.

Scope: Locks, registries, idempotency, cooldowns, symbol serialization, restart behavior.

Out of scope: Selecting a distributed mechanism.

Dependencies: v4.0 supervisor and operations docs.

Acceptance criteria:

- Inventory complete
- Risks mapped to code paths

Test requirements:

- Architecture inventory checks

Evidence requirements:

- Inventory document

## V41-CC-002 - Define distributed coordination requirements

| Field | Value |
|---|---|
| Priority | P1 |
| Status | PLANNED |
| Owner | NOT ASSIGNED |
| Target milestone | NOT DEFINED |

Rationale: Clarify what multi-process support must guarantee.

Scope: Ownership, timeouts, stale locks, recovery, reconciliation, failure cases.

Out of scope: Implementation.

Dependencies: V41-CC-001.

Acceptance criteria:

- Requirements approved
- Failure modes documented

Test requirements:

- Requirements review checklist

Evidence requirements:

- Requirements document

## V41-CC-003 - Select coordination architecture through ADR

| Field | Value |
|---|---|
| Priority | P1 |
| Status | PLANNED |
| Owner | NOT ASSIGNED |
| Target milestone | NOT DEFINED |

Rationale: Prevent premature mechanism selection.

Scope: Evaluate database, Redis, durable idempotency, outbox, command ledger.

Out of scope: Implementation before decision.

Dependencies: V41-CC-001, V41-CC-002.

Acceptance criteria:

- ADR accepted
- Evidence supports selected option

Test requirements:

- ADR option validation tests as applicable

Evidence requirements:

- Accepted ADR

## V41-EP-001 - Inventory NullEventPublisher usage

| Field | Value |
|---|---|
| Priority | P1 |
| Status | PLANNED |
| Owner | NOT ASSIGNED |
| Target milestone | NOT DEFINED |

Rationale: Separate no-delivery behavior from production observability.

Scope: Call sites, metrics, diagnostics, release evidence dependencies.

Out of scope: External publisher implementation.

Dependencies: v4.0 event model.

Acceptance criteria:

- All usage inventoried
- Risks documented

Test requirements:

- Architecture inventory tests

Evidence requirements:

- Inventory document

## V41-EP-002 - Define external publisher contract

| Field | Value |
|---|---|
| Priority | P1 |
| Status | PLANNED |
| Owner | NOT ASSIGNED |
| Target milestone | NOT DEFINED |

Rationale: Make delivery behavior explicit and testable.

Scope: Delivery attempts, failures, retries, duplicates, correlation, status reporting.

Out of scope: Choosing a vendor or storage backend.

Dependencies: V41-EP-001.

Acceptance criteria:

- Contract documented
- Null behavior remains explicit

Test requirements:

- Contract tests
- failure tests

Evidence requirements:

- Proposed ADR/contract doc

## V41-EP-003 - Implement delivery observability and audit

| Field | Value |
|---|---|
| Priority | P1 |
| Status | PLANNED |
| Owner | NOT ASSIGNED |
| Target milestone | NOT DEFINED |

Rationale: Expose event delivery status to operators.

Scope: Metrics, diagnostics, bounded retry reporting, local/external status separation.

Out of scope: Durable event store unless selected.

Dependencies: V41-EP-002.

Acceptance criteria:

- Failures visible
- Retries bounded
- Duplicate delivery defined

Test requirements:

- Integration tests
- metrics tests
- diagnostic tests

Evidence requirements:

- Redacted delivery evidence

## V41-PF-001 - Define benchmark environment and workloads

| Field | Value |
|---|---|
| Priority | P2 |
| Status | PLANNED |
| Owner | NOT ASSIGNED |
| Target milestone | NOT DEFINED |

Rationale: Make performance comparison reproducible.

Scope: Environment, fixtures, warmup, iterations, median and tail metrics.

Out of scope: Threshold selection.

Dependencies: Existing benchmark script.

Acceptance criteria:

- Environment documented
- Workloads representative

Test requirements:

- Benchmark schema tests

Evidence requirements:

- Benchmark definition doc

## V41-PF-002 - Define formal regression thresholds

| Field | Value |
|---|---|
| Priority | P2 |
| Status | PLANNED |
| Owner | NOT ASSIGNED |
| Target milestone | NOT DEFINED |

Rationale: Convert baselines into a release gate.

Scope: Tolerance, noise handling, failure rules, CI/local execution.

Out of scope: Optimization work.

Dependencies: V41-PF-001, historical baselines.

Acceptance criteria:

- Thresholds evidence-based
- Gate fails clearly

Test requirements:

- Threshold evaluation tests
- failure-mode tests

Evidence requirements:

- Threshold ADR and sample report

## V41-RA-001 - Automate release verification summary

| Field | Value |
|---|---|
| Priority | P2 |
| Status | PLANNED |
| Owner | NOT ASSIGNED |
| Target milestone | NOT DEFINED |

Rationale: Reduce manual release reporting effort.

Scope: Generate verification summaries from existing outputs.

Out of scope: Automatic release decisions.

Dependencies: make verify and docs templates.

Acceptance criteria:

- Summary generated
- Human approval remains required

Test requirements:

- Report generation tests

Evidence requirements:

- Generated summary artifact

## V41-RA-002 - Automate manifest verification and evidence packaging

| Field | Value |
|---|---|
| Priority | P2 |
| Status | PLANNED |
| Owner | NOT ASSIGNED |
| Target milestone | NOT DEFINED |

Rationale: Reduce evidence-management errors.

Scope: Manifest validation, hash generation, artifact packaging, redaction checks.

Out of scope: Uploading, pushing, or tagging releases.

Dependencies: Evidence manifest.

Acceptance criteria:

- Hashes verified
- Packaging redacted
- No automatic tag creation

Test requirements:

- Manifest tests
- redaction tests
- no-auto-tag tests

Evidence requirements:

- Packaged evidence output
