# EduTraderAI v4.1 Roadmap

## 1. Document control

| Field | Value |
|---|---|
| Document | EduTraderAI v4.1 Roadmap |
| Status | Initial planning baseline |
| Branch | `feature/edutrader-v4.1` |
| Baseline release | `v4.0.0` |
| Baseline commit | `6a1cf97b9027ceb92242a032bca9b4bb802ff662` |
| Owner | NOT ASSIGNED |
| Target milestone | NOT DEFINED |

This roadmap initializes v4.1 planning from the authorized EduTraderAI v4.0.0
Stable release. It does not authorize implementation by itself.

## 2. v4.0 Stable baseline

EduTraderAI v4.0.0 is the stable baseline for v4.1. The stable tag remains
`v4.0.0` and points to `6a1cf97b9027ceb92242a032bca9b4bb802ff662`. The release
record is preserved in operational documentation and evidence manifests.

The v4.0 baseline includes deterministic manual preview, deterministic manual
submission, supervised scanner execution, operational metrics, local evidence
exports, rollback flags, Alpaca Paper smoke evidence, and accepted deployment
limitations.

## 3. v4.1 objectives

EMERS Trade is the emerging user-facing product identity for this line, while
EduTraderAI remains the existing technical engine. Public commercialization is
outside the immediate v4.1 implementation scope unless separately approved.

v4.1 is an incremental safety and release-operations release over v4.0.0. Its
primary objectives are:

- Add a deterministic Paper-only broker qualification workflow.
- Analyze and improve coordination beyond process-local state.
- Define a production-capable event-publisher observability path.
- Convert performance baselines into formal release gates.
- Reduce manual release evidence work while preserving operator approval.

## 4. Scope

Project Horizon defines the future EMERS product experience and design-system
blueprint. Horizon does not authorize implementation, select a frontend
framework, implement EMERS Score, authorize mobile order submission, or alter
the approved v4.1 engineering sequence. V41-PQ-001 remains the next approved
implementation item.

Project Atlas now provides a directional ecosystem blueprint for future EMERS
Trade product, technology, security, data, broker, commercialization, and
delivery decisions. Atlas does not change the approved v4.1 priorities or
authorize implementation beyond separately approved backlog items.

In scope:

- Paper-only qualification workflow design and implementation.
- Cross-process coordination analysis and architecture decision work.
- Event publisher observability design and implementation path.
- Formal performance threshold design.
- Release automation that packages evidence and supports human review.
- Versioned evidence schema updates where needed.

## 5. Out of scope

Out of scope unless separately authorized:

- Live trading enablement.
- New trading strategies.
- Policy, sizing, or risk-model changes unrelated to qualification safety.
- Broker behavior changes outside qualification-mode requirements.
- Distributed production deployment before coordination is validated.
- Durable event storage selection before evidence-backed ADR approval.
- Automatic stable tagging without explicit human approval.

## 6. Workstreams

### Workstream A - Deterministic Paper Qualification Mode

| Field | Value |
|---|---|
| Priority | P0 |
| Owner | NOT ASSIGNED |
| Target milestone | NOT DEFINED |

Problem statement: v4.0 Alpaca Paper smoke validated broker lifecycle but did
not prove deterministic one-share qualification. The workflow needs a dedicated
Paper-only path that cannot reach live trading and creates self-contained
redacted evidence.

Business value: Reduces release uncertainty and makes broker qualification
repeatable before future paper releases.

Safety value: Ensures qualification cannot accidentally create live orders,
large orders, fills, open orders, or positions.

Dependencies: Existing broker configuration, Alpaca Paper adapter, release
evidence manifest, operator confirmation flow, deterministic service stack.

Implementation risks: Incorrect endpoint routing, accidental live access,
quantity override bypass, order fill risk, duplicate qualification execution,
and incomplete cleanup evidence.

Acceptance criteria:

- Available only when Alpaca Paper is selected.
- Impossible to route to a live endpoint.
- Forces exactly one share.
- Uses a deliberately non-marketable limit order.
- Preserves explicit operator confirmation.
- Preserves risk and policy checks.
- Submits exactly one order.
- Captures broker acknowledgment and status.
- Verifies zero fill.
- Automatically cancels.
- Confirms no open orders and no position.
- Creates redacted immutable JSON evidence and SHA-256.
- Prevents duplicate execution.
- Returns clear PASS / FAIL / BLOCKED result.

Required tests: endpoint guard tests, one-share enforcement, non-marketable
price construction, duplicate prevention, broker acknowledgment/status/cancel
mapping, zero-fill and no-position checks, redaction tests, evidence hash tests,
and architecture boundary tests.

Required evidence: redacted JSON qualification artifact, manifest row, hash
verification output, broker status summary, cancellation confirmation, and no
open-order/no-position confirmation.


Design status: ADR-004 — ACCEPTED AFTER SENTINEL REVIEW. V41-PQ-001 — READY FOR IMPLEMENTATION after separate implementation authorization. The design documents define the accepted state machine, transition table, and test strategy. They do not mark V41-PQ-001 implemented, do not change production behavior, and keep V41-PQ-002 persistence and V41-CP-001 coordination separate.

Design references:

- `docs/adr/ADR-004-PAPER-QUALIFICATION-STATE-MACHINE.md`
- `docs/engineering/V41_PQ_001_DESIGN.md`
- `docs/engineering/V41_PQ_001_TRANSITION_TABLE.md`
- `docs/engineering/V41_PQ_001_TEST_STRATEGY.md`

Implementation status:

- V41-PQ-001A — CORE DOMAIN MODEL AND PURE TRANSITION ENGINE: IMPLEMENTED.
- V41-PQ-001B — APPLICATION QUALIFICATION SERVICE: IMPLEMENTED.
- V41-PQ-001C — QUALIFICATION SCENARIO HARNESS: IMPLEMENTED.
- V41-PQ-001D — QUALIFICATION EVIDENCE ADAPTER: IMPLEMENTED.
- V41-PQ-001E — PAPER WORKFLOW INTEGRATION ARCHITECTURE REVIEW: COMPLETED.
- V41-PQ-001F1 — INTEGRATION CONTRACTS AND COMPATIBILITY TRANSLATION: IMPLEMENTED.
- V41-PQ-001F2 — PAPER QUALIFICATION FACADE: IMPLEMENTED.
- V41-PQ-001F3 — SHADOW-MODE PAPER QUALIFICATION INVOCATION: IMPLEMENTED.
- V41-PQ-001F4A — QUALIFICATION RUNTIME INTEGRATION BOUNDARY: IMPLEMENTED.
- V41-PQ-001F4B — CONTROLLED SHADOW RUNTIME WIRING: IMPLEMENTED.
- V41-PQ-001F4C — SHADOW OBSERVATION VALIDATION HARNESS: IMPLEMENTED.
- V41-PQ-001F4D — SHADOW READINESS ASSESSMENT: IMPLEMENTED.
- V41-PQ-001F5A — PAPER EXECUTOR ARCHITECTURE REVIEW: COMPLETED.
- V41-PQ-001F5B — PAPER EXECUTOR CONTRACTS: IMPLEMENTED.
- V41-PQ-001F5C — EXECUTION ELIGIBILITY CORE: IMPLEMENTED.
- V41-PQ-001F5D0 — PAPER EXECUTION LIFECYCLE DESIGN: COMPLETED.
- SENTINEL ADR-006 REVIEW — COMPLETED.
- ADR-005 — PAPER EXECUTION MODEL: ACCEPTED.
- ADR-006 — PAPER EXECUTION LIFECYCLE: ACCEPTED.
- V41-PQ-001F5D1 — EXECUTION LIFECYCLE CORE: IMPLEMENTED.
- V41-PQ-001F5D2 — DETERMINISTIC PAPER DRY-RUN EXECUTOR: IMPLEMENTED.
- V41-PQ-001F5E0 — PERSISTENCE ARCHITECTURE REVIEW: COMPLETED.
- ADR-007 — EXECUTION PERSISTENCE AND IDEMPOTENCY: ACCEPTED.
- SENTINEL ADR-007 REVIEW — COMPLETED.
- V41-PQ-001F5E1A — PERSISTENCE CONTRACTS AND UNIT-OF-WORK PORTS: IMPLEMENTED.
- V41-PQ-001F5E1B — DETERMINISTIC IN-MEMORY REFERENCE ADAPTER: IMPLEMENTED.
- V41-PQ-001F5E-SPIKE — SQLITE/POSTGRESQL EXECUTION DURABILITY COMPARISON: COMPLETED.
- V41-PQ-001F5E2A — SQLITE DURABLE ADAPTER DESIGN: COMPLETED.
- ADR-008 — SQLITE EXECUTION DURABLE ADAPTER: PROPOSED.
- V41-PQ-001 overall status: IN PROGRESS.
- V41-PQ-001E review disposition: ACCEPTED WITH CONDITIONS.
- V41-PQ-001F5A review disposition: ACCEPTED WITH CONDITIONS.
- Next recommended slice: SENTINEL ADR-008 REVIEW.
- V41-PQ-001F4B connects exactly one approved Paper runtime observation point, calls only `QualificationRuntimeIntegrationBoundary`, never calls the shadow runner, facade, or service directly, remains disabled by default, uses an explicit typed Paper-only gate, never executes returned actions, never alters legacy decisions, provides instant rollback by disabling or removing one narrow call site, preserves broker, simulator, scanner, supervisor, and UI behavior, and proves zero behavioral impact when disabled and zero consequential impact when enabled.
- V41-PQ-001F4C adds an in-memory validation harness that consumes completed boundary results only, aggregates immutable validation facts, detects duplicates and conflicts, evaluates repeatability and continuity counters, produces deterministic summaries, remains unwired from production runtime, and does not authorize runtime execution.
- V41-PQ-001F4D consumes immutable F4C validation summaries, defines explicit advisory readiness criteria, distinguishes READY_FOR_NEXT_PHASE, NOT_READY, and INSUFFICIENT_EVIDENCE, requires zero identity and authority violations under strict policy, requires zero nondeterministic conflicts, requires deterministic replay, defines minimum observation counts, defines permitted and prohibited mismatch categories, remains advisory only, does not authorize runtime execution, does not invoke brokers, does not persist, does not add Live support, and does not mark V41-PQ-001 complete.
- V41-PQ-001F5A completed the Paper executor architecture review, accepts execution as a separate bounded context, keeps readiness advisory only, requires explicit Paper execution approval, deterministic idempotency, optimistic execution revision, unknown-outcome handling, reconciliation, market-capability isolation, broker isolation, Paper-only mode, and structural Live exclusion, and does not implement executor code, contracts, broker adapters, persistence, runtime wiring, broker calls, simulator access, scanner changes, supervisor changes, or execution authority.
- V41-PQ-001F5B implements Paper executor contracts only: immutable records, enums, typed failures, deterministic identities, deterministic canonical serialization, centralized SHA-256 fingerprints, Paper-only mode, a dedicated execution revision, inert commands, normalized receipts, normalized failures, architecture-boundary tests, and focused contract tests. F5B does not wire runtime, call brokers, persist, reserve idempotency, enforce stale revisions, evaluate approval, evaluate market capabilities, add Live behavior, or mark V41-PQ-001 complete.
- V41-PQ-001F5C implements a pure execution eligibility core using F5B contracts. It adds immutable eligibility policy and result contracts, deterministic criterion evaluation, explicit `ELIGIBLE`, `INELIGIBLE`, and `INDETERMINATE` decisions, explicit evaluation timestamps with no hidden clock, approval-evidence checks, policy-snapshot compatibility checks, unresolved external prerequisite representation, and `pep-` / `per-` fingerprints. F5C remains advisory only: `ELIGIBLE` is not authorization, `execution_authorized` remains false, `action_executed` remains false, and no runtime, broker, persistence, durable idempotency reservation, stale-revision storage check, market-capability evaluation, risk evaluation, account evaluation, emergency-stop lookup, readiness authority transfer, or Live behavior was added.
- V41-PQ-001F5D0 completes the Paper execution lifecycle design only. Project Sentinel accepted ADR-006 after review, with state count 22, transition count 30, explicit command/aggregate/broker-order terminality, replay and duplicate semantics, unknown-outcome and reconciliation-entry rules, cancellation and replacement safety, partial-fill handling, dry-run isolation, and the recommendation to implement V41-PQ-001F5D1 lifecycle core before V41-PQ-001F5D2 deterministic dry-run executor. F5D0 adds no production lifecycle state machine, executor, dry-run executor, broker port, broker adapter, persistence, runtime wiring, event publisher, metrics, logging, configuration, dependency, or Live behavior.
- V41-PQ-001F5D1 implements the pure Paper execution lifecycle core accepted by ADR-006: exactly 22 states, exactly 30 transition specifications, immutable aggregate/input/context/specification/decision contracts, expected-revision validation, deterministic replay and conflict decisions, unknown-outcome and reconciliation-required restrictions, cancellation/replacement guards, partial-fill monotonicity, and descriptive side-effect/evidence intents only. F5D1 adds no executor, dry-run executor, broker port, broker adapter, broker call, persistence, simulator access, runtime wiring, qualification authority transfer, readiness authority transfer, or Live behavior.
- V41-PQ-001F5D2 implements a deterministic Paper dry-run executor. It composes F5C eligibility and F5D1 lifecycle transitions, introduces a separate `DRY_RUN` effect model, produces immutable dry-run requests, results, steps, receipts, and failures, stops successful submit simulation at `READY_FOR_DISPATCH`, returns `WOULD_DISPATCH` as simulation only, and keeps execution authorization, action execution, broker access, simulator access, persistence access, runtime mutation, and Live authority false. F5D2 adds no broker port, broker adapter, broker call, simulator access, persistence, durable idempotency, runtime wiring, event publisher, metrics, logging, UI, API, CLI, dependency, configuration, or Live behavior.
- V41-PQ-001F5E0 completes the persistence and idempotency architecture review. Sentinel ADR-007 review is completed. ADR-007 is Accepted. The storage decision is AUTHORIZE_COMPARATIVE_SPIKE, F5E1A and F5E1B are implemented within their bounded non-durable scopes, durable persistence remains unimplemented, durable idempotency remains unimplemented, broker execution remains prohibited, Paper trading is not enabled, and Live remains unsupported.
- V41-PQ-001F5E1A implements storage-neutral persistence contracts and unit-of-work ports only. It adds immutable execution aggregate, command, idempotency, transition, broker-reference, receipt, failure, approval, and reconciliation record contracts; immutable repository result, replay, conflict, restart-discovery, and unit-of-work result contracts; repository ports; and unit-of-work/session ports. It implements no adapter, in-memory repository, database, schema, migration, durable storage, durable idempotency, broker port, broker adapter, runtime wiring, Paper trading enablement, or Live support.
- Do not proceed directly to a broker side-effect executor.
- Broker execution, runtime integration beyond controlled shadow observation, persistence, durable evidence storage, and cross-process coordination remain pending and are not part of V41-PQ-001A, V41-PQ-001B, V41-PQ-001C, V41-PQ-001D, V41-PQ-001E, V41-PQ-001F1, V41-PQ-001F2, V41-PQ-001F3, V41-PQ-001F4A, V41-PQ-001F4B, V41-PQ-001F4C, V41-PQ-001F4D, V41-PQ-001F5A, or V41-PQ-001F5B.
- Implementation report: `docs/engineering/V41_PQ_001A_IMPLEMENTATION_REPORT.md`.
- Implementation report: `docs/engineering/V41_PQ_001B_IMPLEMENTATION_REPORT.md`.
- Implementation report: `docs/engineering/V41_PQ_001C_IMPLEMENTATION_REPORT.md`.
- Implementation report: `docs/engineering/V41_PQ_001D_IMPLEMENTATION_REPORT.md`.
- Architecture review: `docs/engineering/V41_PQ_001E_INTEGRATION_ARCHITECTURE_REVIEW.md`.
- Implementation report: `docs/engineering/V41_PQ_001F1_IMPLEMENTATION_REPORT.md`.
- Implementation report: `docs/engineering/V41_PQ_001F2_IMPLEMENTATION_REPORT.md`.
- Implementation report: `docs/engineering/V41_PQ_001F3_IMPLEMENTATION_REPORT.md`.
- Implementation report: `docs/engineering/V41_PQ_001F4A_IMPLEMENTATION_REPORT.md`.
- Observation-point decision: `docs/engineering/V41_PQ_001F4B_OBSERVATION_POINT_DECISION.md`.
- Implementation report: `docs/engineering/V41_PQ_001F4B_IMPLEMENTATION_REPORT.md`.
- Implementation report: `docs/engineering/V41_PQ_001F4C_IMPLEMENTATION_REPORT.md`.
- Implementation report: `docs/engineering/V41_PQ_001F4D_IMPLEMENTATION_REPORT.md`.
- Architecture review: `docs/engineering/V41_PQ_001F5A_PAPER_EXECUTOR_ARCHITECTURE_REVIEW.md`.
- Implementation report: `docs/engineering/V41_PQ_001F5B_IMPLEMENTATION_REPORT.md`.
- Implementation report: `docs/engineering/V41_PQ_001F5D1_IMPLEMENTATION_REPORT.md`.
- Implementation report: `docs/engineering/V41_PQ_001F5D2_IMPLEMENTATION_REPORT.md`.
- Architecture review: `docs/engineering/V41_PQ_001F5E0_PERSISTENCE_ARCHITECTURE_REVIEW.md`.


### Workstream B - Cross-process Coordination

| Field | Value |
|---|---|
| Priority | P1 |
| Owner | NOT ASSIGNED |
| Target milestone | NOT DEFINED |

Problem statement: v4.0 coordination is process-local. This is acceptable for a
single-process supervised Paper deployment but insufficient for multiple workers
or multiple broker submitters.

Business value: Expands safe deployment options and reduces operator reliance on
single-process constraints.

Safety value: Reduces duplicate-order, stale-lock, restart, replay, and partial
failure risk.

Dependencies: ExecutionSupervisor, idempotency keys, symbol locks, cooldown
registry, broker reconciliation, metrics, and future persistence decisions.

Implementation risks: Split-brain locking, stale locks, unbounded retries,
transaction boundary mistakes, and accidental behavior changes in the current
single-process path.

Acceptance criteria:

- Current process-local locks and registries are inventoried.
- Single-process and multi-process deployment models are defined.
- Duplicate-order and concurrency risks are documented.
- External coordination mechanisms are evaluated with evidence.
- Idempotency ownership is defined.
- Failure recovery, stale-lock handling, timeout behavior, and reconciliation
after partial failure are specified.
- Current single-process behavior is preserved.

Required tests: process-local compatibility tests, duplicate request tests,
stale-lock and timeout tests, restart/reconciliation tests, architecture tests,
and failure-injection tests once a mechanism is selected.

Required evidence: inventory document, ADR with option analysis, deterministic
integration evidence, and reconciliation evidence.

### Workstream C - Event Publisher Observability

| Field | Value |
|---|---|
| Priority | P1 |
| Owner | NOT ASSIGNED |
| Target milestone | NOT DEFINED |

Problem statement: v4.0 validates event attempts but uses `NullEventPublisher`,
which has no external delivery, durability, replay, or recovery semantics.

Business value: Improves production observability and operator confidence.

Safety value: Makes event-delivery failures visible and separates local audit
from external delivery state.

Dependencies: event model, EventPublisher interface, operational metrics,
evidence exports, and release diagnostics.

Implementation risks: duplicate delivery, silent delivery failure, unbounded
retry loops, loss of correlation IDs, and confusing null-delivery status with
successful external publication.

Acceptance criteria:

- `NullEventPublisher` remains available and clearly identified as no external
delivery.
- External publisher behavior is documented.
- Delivery attempts are auditable.
- Failures are visible.
- Retries are bounded.
- Duplicate delivery behavior is defined.
- Event identifiers support tracing.
- Local audit and external delivery status are distinguishable.
- Release-critical monitoring does not silently depend on null delivery.

Required tests: publisher contract tests, failure visibility tests, bounded retry
tests, duplicate-delivery tests, correlation tests, metrics tests, and no-secret
serialization tests.

Required evidence: publisher contract documentation, ADR, test output,
redacted delivery evidence, and diagnostic snapshot.

### Workstream D - Formal Performance Thresholds

| Field | Value |
|---|---|
| Priority | P2 |
| Owner | NOT ASSIGNED |
| Target milestone | NOT DEFINED |

Problem statement: v4.0 has benchmark baselines but no formal pass/fail
performance threshold.

Business value: Makes release qualification more objective and repeatable.

Safety value: Prevents unnoticed latency regressions in planning, preview,
submission, supervisor, and scanner decision paths.

Dependencies: benchmark script, release verification flow, historical benchmark
evidence, CI or local release-gate capability.

Implementation risks: noisy local measurements, hardware variability,
overly-tight thresholds, overly-loose thresholds, and false failures in CI.

Acceptance criteria:

- Benchmark environment is defined.
- Representative workloads are defined.
- Warm-up behavior and repetitions are defined.
- Median and tail metrics are defined.
- Permitted regression tolerance is defined through evidence.
- Noise-handling rules are documented.
- Memory/resource expectations are considered where relevant.
- CI or release-gate execution is documented.
- Historical benchmark evidence is preserved.

Required tests: benchmark script tests, JSON schema tests, threshold evaluation
tests, and release-gate failure-mode tests.

Required evidence: benchmark output, threshold ADR, comparison report, and
release verification summary.

### Workstream E - Release Automation

| Field | Value |
|---|---|
| Priority | P2 |
| Owner | NOT ASSIGNED |
| Target milestone | NOT DEFINED |

Problem statement: v4.0 release qualification required substantial manual
evidence collection and reconciliation.

Business value: Reduces operator burden and improves consistency.

Safety value: Lowers risk of incomplete evidence, stale manifest rows, or
accidental automatic release actions.

Dependencies: release verification command, evidence manifest, operational docs,
qualification workflow, and human approval record.

Implementation risks: over-automation, accidental tag creation, evidence
redaction mistakes, and hiding operator judgment behind generated reports.

Acceptance criteria:

- Automated verification report is available.
- Manifest verification and evidence packaging are automated.
- Release-readiness report generation is supported.
- Paper qualification evidence packaging is supported.
- GO / NO-GO checklist generation is supported.
- Explicit human approval gate is preserved.
- Automation cannot automatically create Stable tags.

Required tests: report generation tests, manifest verification tests, redaction
tests, no-auto-tag tests, and approval-gate tests.

Required evidence: generated release summary, manifest verification output,
redaction proof, and approval-gate proof.

## 7. Acceptance criteria

v4.1 release-level acceptance criteria:

- All v4.0 tests remain passing.
- No regression below the current coverage floor.
- All new features have unit, integration, and architecture tests as applicable.
- Deterministic Paper qualification completes without manual broker cleanup.
- Qualification mode cannot access a live endpoint.
- Exactly one share is enforced.
- Duplicate execution is prevented.
- External event-publisher behavior is observable.
- Multi-process restrictions are either removed through validated coordination or
  retained explicitly.
- Formal performance gate is documented and executable.
- Evidence manifest remains complete and hash-valid.
- Operational documentation is updated.
- Final Paper qualification is completed before v4.1 Stable authorization.

## 8. Test strategy

The v4.1 test strategy preserves the v4.0 verification gate and adds focused
coverage for each new boundary. Required test layers include:

- Unit tests for deterministic qualification calculations and state transitions.
- Adapter tests for Alpaca Paper-only endpoint enforcement and broker lifecycle
mapping.
- Integration tests using fake brokers and simulator-safe fixtures.
- Architecture tests proving core modules do not import broker adapters,
Streamlit, scanners, or persistence outside approved boundaries.
- Evidence serialization and redaction tests.
- Release automation tests for manifest and report generation.

Live endpoints must not be used in ordinary automated tests.

## 9. Evidence strategy

Evidence must remain redacted, immutable, hash-addressed, and manifest-tracked.
Existing v4.0 evidence formats should remain readable. New evidence schemas must
be versioned and should include explicit schema names, schema versions, UTC
creation timestamps, repository identity, release identity, redaction status,
and SHA-256 references.

## 10. Migration and compatibility

v4.1 is an incremental release over v4.0.0. Existing v4.0 Paper workflows must
remain compatible unless explicitly deprecated. No live-trading capability may be
introduced implicitly. Default deployment remains constrained until
cross-process coordination is validated. Database or configuration migrations
require rollback instructions. Security-sensitive settings must default to the
safest mode.

## 11. Risks

| Risk | Impact | Initial treatment |
|---|---|---|
| Qualification accidentally reaches live endpoint | High | Paper-only hard gates and tests |
| One-share enforcement bypassed | Medium | Dedicated qualification contract and regression tests |
| Distributed coordination selected without evidence | Medium | ADR required before selection |
| Event publishing appears successful when null delivery is active | Medium | Explicit diagnostics and publisher status |
| Performance gate is too noisy | Medium | Evidence-based tolerance and noise rules |
| Automation creates release action without human approval | High | Explicit no-auto-tag acceptance criterion |

## 12. Milestones

| Milestone | Workstreams | Owner | Target milestone |
|---|---|---|---|
| Qualification design complete | A | NOT ASSIGNED | NOT DEFINED |
| Qualification implementation validated | A | NOT ASSIGNED | NOT DEFINED |
| Coordination ADR complete | B | NOT ASSIGNED | NOT DEFINED |
| Event publisher ADR complete | C | NOT ASSIGNED | NOT DEFINED |
| Performance threshold proposal complete | D | NOT ASSIGNED | NOT DEFINED |
| Release automation proposal complete | E | NOT ASSIGNED | NOT DEFINED |
| v4.1 release candidate hardening | A-E | NOT ASSIGNED | NOT DEFINED |

## 13. Definition of Done

v4.1 is done when all approved workstreams are implemented or explicitly
deferred, the v4.0 workflows remain compatible, the release verification gate is
green, new tests and evidence are complete, operational documentation is updated,
and the operator completes a final v4.1 release authorization process.

- V41-PQ-001F5E1B implements the deterministic, process-local in-memory persistence reference adapter. It implements the F5E1A repository ports and unit-of-work semantics with staged transaction snapshots, atomic commit validation, rollback, exact command replay, logical idempotency replay/conflict, optimistic revision checks, append-only transition journals, broker-reference uniqueness, and restart-discovery queries over current in-memory state. It implements no durable persistence, database, schema, migration, filesystem storage, cross-process coordination, broker port, broker adapter, runtime wiring, Paper trading enablement, or Live support.

- V41-PQ-001F5E-SPIKE completed isolated SQLite/PostgreSQL durability comparison. Storage decision: SELECT_SQLITE_WITH_MANDATORY_POSTGRESQL_MIGRATION_TRIGGER. SQLite passed 30/30 executable synthetic scenarios under strict local Paper constraints. PostgreSQL runtime execution was unavailable and remains statically assessed only. Durable persistence remains unimplemented, production database connection remains absent, broker execution remains prohibited, Paper trading is not enabled, V41-PQ-001 remains in progress, and Live remains unsupported.

- V41-PQ-001F5E2A completed the SQLite durable adapter design as documentation only. ADR-008 is Proposed and ready for Sentinel review. The design defines a local single-machine SQLite deployment envelope, local-filesystem rule, network-filesystem prohibition, single application authority, WAL/foreign-key/busy-timeout requirements, `BEGIN IMMEDIATE` write transactions, exact aggregate CAS, append-only transition journal protections, migration checksums, startup validation, backup/restore validation, corruption handling, and mandatory PostgreSQL migration triggers. No production SQLite adapter, database schema deployment, migration runner, runtime wiring, broker port, broker adapter, broker call, Paper trading enablement, or Live support was added.
