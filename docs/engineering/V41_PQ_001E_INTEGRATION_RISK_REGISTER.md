# V41-PQ-001E Integration Risk Register

## Severity scale

- `CRITICAL`: could permit Live trading, duplicate broker effects, state
  corruption, or uncontained security failure.
- `MAJOR`: blocks safe consequential integration or creates material
  qualification ambiguity.
- `MINOR`: should be resolved but does not block a no-effect integration slice.
- `NOTE`: tracked design observation.

## Risk register

| Risk ID | Title | Description | Source component | Trigger | Likelihood | Impact | Severity | Detection | Mitigation | Containment | Rollback | Owner | Phase | Blocking status | Verification test |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| PQE-RISK-001 | Duplicate broker submission | Legacy submission and qualification executor both submit the same intended order | `app.py`, `submit_paper_order`, future executor | Dual-path cutover error | Medium | High | CRITICAL | Broker order count, idempotency records | Single side-effect executor; fail-closed flag | Stop and reconcile | Disable flag; do not legacy-submit after uncertain send | Integration owner | F4 | Blocking for broker-effect slices | One-and-only-one submission test |
| PQE-RISK-002 | Duplicate cancellation | Bulk and targeted cancellation paths both act on same order | `PaperBroker.cancel_all_orders`, future cancellation adapter | Operator emergency action during qualification | Medium | Medium | MAJOR | Broker status/evidence mismatch | Targeted cancellation contract; operator warning | Preserve run and require reconciliation | Stop new commands | Integration owner | F6 | Blocking for cancellation automation | One-and-only-one cancellation test |
| PQE-RISK-003 | Restart loss | In-memory state loses active qualification run | Qualification repository | Process restart before persistence | High | High | MAJOR | Missing run after restart | Keep consequential integration disabled until persistence or explicit acceptance | Mark run unresolved if evidence exists | Disable qualification workflow | V41-PQ-002 owner | F2-F6 | Blocking for broad rollout | Restart limitation test |
| PQE-RISK-004 | Non-durable idempotency | Idempotency records are not restart-safe | `QualificationRunRepository` port without durable adapter | Retry after restart | High | High | MAJOR | Duplicate idempotency key absent | Durable repository in V41-PQ-002; no-effect early slices | Block replay-sensitive action | Disable flag | V41-PQ-002 owner | F2-F6 | Blocking for consequential default-on | Replay-after-restart test |
| PQE-RISK-005 | Stale broker observation | Old broker status updates current run | Observation normalizer | Delayed broker read | Medium | High | MAJOR | Expected revision mismatch | Include revision and object reference | Reject stale observation | Preserve run | Integration owner | F5 | Blocking for observation integration | Stale observation test |
| PQE-RISK-006 | Out-of-order observation | Fill/cancel observation arrives before ACK | Observation normalizer | Broker lifecycle race | Medium | High | MAJOR | Invalid transition | Route through `PaperQualificationService` only | Move to unresolved/reconciliation when appropriate | Stop executor | Integration owner | F5/F6 | Blocking for observation integration | Out-of-order observation test |
| PQE-RISK-007 | Partial fill ambiguity | Root broker protocol does not expose partial-fill details | `PaperBroker` | Paper broker partial fill | Low | High | MAJOR | Missing normalized fill facts | Add observation capability or exclude fill scenario | Reconciliation required | Abort/no new commands | Broker adapter owner | F6 | Blocking for fill scenario | Partial-fill normalization test |
| PQE-RISK-008 | Cancellation after fill | Cancellation requested after broker already filled | Broker lifecycle | Fast fill | Low | High | MAJOR | Broker reports filled on cancel/read | Observe fill before cancellation proof | Reconciliation required | Stop and operator review | Broker adapter owner | F6 | Blocking for auto-cancel | Cancel-after-fill test |
| PQE-RISK-009 | Unresolved external effect | Network/error occurs after possible send | Side-effect executor | Exception around broker submission | Medium | High | CRITICAL | Missing ACK with possible broker mutation | Treat as `UNRESOLVED`; reconcile before retry | Disable submissions | Stop and reconcile | Integration owner | F4/F6 | Blocking for broker-effect slice until handled | Uncertain submission test |
| PQE-RISK-010 | Reconciliation unavailable | Current runtime lacks targeted order lookup/status history | `PaperBroker` | Need to prove order outcome | High | High | MAJOR | Capability inventory | Add read-only observation adapter before execution | Do not enable broker effects | Disable flag | Integration owner | F6 | Blocking for consequential qualification | Reconciliation capability test |
| PQE-RISK-011 | Evidence divergence | Operational event/audit and qualification evidence disagree | Events, metrics, evidence recorder | Dual emission | Medium | Medium | MAJOR | Correlation trace comparison | Qualification evidence authoritative | Preserve both; mark discrepancy | Disable evidence dual-write | Evidence owner | F7 | Blocking for acceptance evidence | Evidence trace consistency test |
| PQE-RISK-012 | Evidence duplication | Replay records duplicate evidence | Qualification service/repository | Idempotent replay | Low | Medium | MINOR | Evidence record count | Replayed service result suppresses evidence intents | Safe replay | None | Qualification owner | F1+ | Not blocking F1 | Replay evidence suppression test |
| PQE-RISK-013 | Feature flag misuse | Consequential path enabled accidentally | Future config | Missing or wrong flag | Medium | High | CRITICAL | Platform health/config validation | Default false; fail closed; Paper-only allowlist | Refuse action | Disable flag | Platform owner | F3/F4 | Blocking for runtime integration | Flag default/fail-closed tests |
| PQE-RISK-014 | Paper/Live leakage | Qualification path accepts a live broker | Broker config/facade | Wrong broker injection | Low | Critical | CRITICAL | Negative integration tests | `broker.is_paper` guard and endpoint checks | Refuse before command/effect | No fallback to live | Platform owner | F1/F2 | Blocking all runtime integration | Live broker refusal test |
| PQE-RISK-015 | Emergency-stop race | Stop becomes active after qualification command but before send | Runtime guard source | Operator triggers emergency stop | Medium | High | MAJOR | Guard re-check at executor | Check before command and immediately before effect | Block consequential action | Disable executor | Runtime owner | F4 | Blocking for send/cancel | Emergency-stop race test |
| PQE-RISK-016 | Retry amplification | Retry loop submits or cancels repeatedly | Executor/retry policy | Port failure/retry | Medium | High | CRITICAL | Broker call count | No blind retries; use retry classification | Reconcile first | Stop retries | Integration owner | F4/F6 | Blocking for broker effects | Retry amplification test |
| PQE-RISK-017 | Correlation loss | Events/evidence cannot reconstruct lifecycle | Runtime/facade | New IDs generated per step | Medium | Medium | MAJOR | Evidence chain inspection | Preserve correlation ID from start | Block finalization if missing | Stop run | Facade owner | F1/F2 | Blocking for evidence acceptance | Correlation propagation test |
| PQE-RISK-018 | Revision conflict | Runtime sends command with stale revision | Facade/service | Concurrent operator action | Medium | Medium | MAJOR | Service rejection | Service owns revision checks | Preserve state | Retry only after reload | Facade owner | F2 | Not blocking F1 | Stale revision test |
| PQE-RISK-019 | Operator-message inconsistency | Runtime says success while qualification says pending/unresolved | Presentation mapping | Incorrect UI translation | Medium | High | MAJOR | UI/result contract tests | Map from service result only | Show safe unresolved message | Disable facade | Presentation owner | F3 | Blocking for UI rollout | Message mapping test |
| PQE-RISK-020 | Legacy tests mask assumptions | Existing tests pass without exercising qualification path | Test suite | Feature flag disabled | High | Medium | MINOR | Coverage/architecture review | Add focused qualification integration tests | Do not claim coverage | None | QA owner | F1+ | Not blocking F1 | Integration test presence check |
| PQE-RISK-021 | Simulator differs from Alpaca Paper | Simulator accepts order/status differently than Paper | `SimulatedPaperBroker`, `AlpacaPaperBroker` | Paper smoke behavior differs | Medium | Medium | MAJOR | Adapter parity tests | Normalize common subset; environment-specific evidence | Mark inconclusive | Disable Alpaca qualification | Broker adapter owner | F5/F8 | Blocking for Alpaca acceptance | Simulator/Alpaca parity test |
| PQE-RISK-022 | Rollback with active run | Disabling flag hides active non-terminal qualification run | Feature flag/facade | Operator rollback | Medium | High | MAJOR | Health report active-run check | Rollback preserves run and blocks unsafe fallback | Require reconcile/manual review | Disable new starts only | Platform owner | F3/F4 | Blocking for flag rollout | Active-run rollback test |
| PQE-RISK-023 | Facade becomes second state machine | Facade branches on state and mutates behavior independently | Future facade | Overgrown integration layer | Medium | High | MAJOR | Architecture/code review | Facade only maps commands/results | Reject design | Refactor before enablement | Architecture owner | F2 | Blocking for F2 acceptance | Facade no-state-machine test |

## Structured findings

### PQE-FIND-001 — Missing targeted reconciliation capability

- Severity: MAJOR
- Affected component: `broker.base.PaperBroker`
- Evidence: current protocol exposes `get_open_orders`, `get_positions`, and
  bulk controls, but no targeted order lookup or order-status history.
- Consequence: qualification cannot safely resolve uncertain broker effects.
- Required resolution: add or wrap a read-only targeted observation capability
  before broker-effect qualification execution.
- Owner: integration/broker adapter owner.
- Target phase: F5/F6.
- Blocking status: blocking for consequential qualification execution; not
  blocking F1 contracts.

### PQE-FIND-002 — Missing targeted cancellation capability

- Severity: MAJOR
- Affected component: `PaperBroker.cancel_all_orders`
- Evidence: only bulk cancel is exposed.
- Consequence: a qualification run cannot prove it cancelled only its own order.
- Required resolution: targeted cancellation or explicit scenario design that
  does not require automated targeted cancellation.
- Owner: broker adapter owner.
- Target phase: F6.
- Blocking status: blocking for cancellation-cleanup scenario execution.

### PQE-FIND-003 — Persistence deferred

- Severity: MAJOR
- Affected component: `QualificationRunRepository`
- Evidence: production persistence remains deferred to V41-PQ-002.
- Consequence: restart-safe idempotency and recovery cannot be claimed.
- Required resolution: keep early integration no-effect or explicitly accepted
  as process-local only.
- Owner: V41-PQ-002 owner.
- Target phase: V41-PQ-002.
- Blocking status: blocking for broad default-on rollout.

### PQE-FIND-004 — Paper/Live guard is strong but must be repeated

- Severity: MINOR
- Affected component: `AlpacaPaperBroker`, `PaperBrokerExecutionAdapter`,
  future facade.
- Evidence: current adapter uses `paper=True` and rejects non-Paper brokers.
- Consequence: future facade still needs its own guard to prevent bypass.
- Required resolution: duplicate Paper-only guard at facade and executor.
- Owner: integration owner.
- Target phase: F1/F2.
- Blocking status: blocking for runtime integration tests, not for docs.

### PQE-FIND-005 — Existing observability is not durable qualification evidence

- Severity: NOTE
- Affected component: `NullEventPublisher`, operational metrics, `AuditLog`.
- Evidence: publisher may be no-op, metrics are process-local, audit is scanner
  JSONL.
- Consequence: these sources cannot be qualification authority.
- Required resolution: treat canonical qualification evidence as authoritative.
- Owner: evidence owner.
- Target phase: F7.
- Blocking status: not blocking F1.

## Blocking risks for V41-PQ-001F

For V41-PQ-001F1, no blocking risk remains if the slice is limited to contracts
and compatibility translation with no broker effects.

For any slice that submits, cancels, or finalizes qualification from broker
truth, the following risks are blocking until resolved or formally deferred with
an explicit no-effect scope:

- PQE-RISK-001 duplicate broker submission.
- PQE-RISK-009 unresolved external effect.
- PQE-RISK-010 reconciliation unavailable.
- PQE-RISK-013 feature flag misuse.
- PQE-RISK-014 Paper/Live leakage.
- PQE-RISK-015 emergency-stop race.
- PQE-RISK-016 retry amplification.
- PQE-RISK-022 rollback with active run.
