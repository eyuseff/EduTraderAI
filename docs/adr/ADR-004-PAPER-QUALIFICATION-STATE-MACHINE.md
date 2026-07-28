# ADR-004: Paper Qualification State Machine

## 1. Title

Paper Qualification State Machine for EMERS Trade v4.1.

## 2. Status

Proposed.

This ADR is intentionally not Accepted. It is a review artifact for V41-PQ-001 and does not authorize implementation.

## 3. Date

2026-07-28.

## 4. Decision owners

- Product and engineering owner: EMERS / EduTraderAI operator.
- Reviewers: future v4.1 implementation reviewers.
- Implementation owner: not assigned.

## 5. Related roadmap item

V41-PQ-001 — Design Paper qualification state machine.

Related deferred items:

- V41-PQ-002 — Persistence implementation for qualification evidence and restart recovery.
- V41-CP-001 — Cross-process coordination and multi-process safety.

## 6. Context

EduTraderAI v4.0 provides a validated stable baseline: deterministic manual preview, deterministic manual submission, supervised scanner execution, local operational metrics, redacted evidence exports, rollback flags, and Alpaca Paper validation evidence. v4.1 must introduce deterministic Paper qualification without weakening human approval, broker truth, evidence completeness, duplicate prevention, safe failure, release discipline, or deterministic testing.

The state machine governed by this ADR qualifies a Paper execution path. It does not authorize live trading, automatic trading expansion, multi-user approval, mobile submission, additional brokers, production cloud services, or broker behavior outside a separately approved Paper-qualification workflow.

## 7. Problem statement

The v4.0 platform can preview and submit Paper orders, publish domain events, collect process-local metrics, and reconcile operational evidence during validation. However, Paper qualification itself is not represented as an explicit deterministic lifecycle. Qualification currently exists as release procedure and documentation, supported by services and evidence, rather than as a first-class state machine with allowed transitions, guards, idempotency, recovery rules, and qualification-result semantics.

Without an explicit state machine, v4.1 cannot safely prove that Paper qualification progressed through required states, blocked invalid transitions, distinguished broker acknowledgment from execution, handled unresolved broker states conservatively, or produced required evidence for every material transition.

## 8. Current implementation findings

### CURRENT FACT — Paper workflow composition exists outside the deterministic core

- `app.py:441-515` renders the Paper Order flow, creates a correlation ID, calls `preview_paper_order`, then calls `submit_paper_order` only after the operator enters `PAPER TRADE`.
- `adapters/paper_order_preview.py:60-98` chooses deterministic preview when the feature flag is enabled and returns the existing presentation-facing `RiskDecision` shape.
- `adapters/paper_order_submission.py:29-93` chooses deterministic submission when enabled, validates the `PAPER TRADE` confirmation text, builds an expected plan from the displayed preview, recomputes from a fresh broker snapshot, and delegates through `SubmitTradeService`.

### OBSERVED LIMITATION

The workflow uses preview/submission result objects and operator text confirmation, but it does not persist or expose a Paper-qualification run state such as `PRECHECK_PENDING`, `APPROVAL_PENDING`, `SUBMISSION_PENDING`, `ACKNOWLEDGED`, `RECONCILIATION_REQUIRED`, or `QUALIFIED`.

### PROPOSED V4.1 CHANGE

Introduce a Paper-qualification state machine that owns qualification-run state, transition validation, operator-visible state messages, evidence requirements, idempotency, and recovery semantics without changing the trading planner, sizing, risk policies, broker adapters, or existing v4.0 order submission behavior until implementation is separately approved.

### CURRENT FACT — Broker protocols distinguish root Paper broker from Volcanes broker port

- `broker/base.py:8-45` defines immutable `AccountSnapshot`, `BrokerPosition`, and `BrokerOrder` records.
- `broker/base.py:47-73` defines `PaperBroker`, including `get_account`, `get_positions`, `get_open_orders`, `submit_bracket_order`, `cancel_all_orders`, and `close_all_positions`.
- `volcanoes/execution/broker.py:10-27` defines the Volcanes `Broker` port used by `ExecutionPipeline`.
- `adapters/paper_broker_execution.py:13-57` translates the root Paper broker into the Volcanes broker port and rejects non-Paper brokers.

### OBSERVED LIMITATION

The existing `BrokerOrder.status` is a broker-status string, not a qualification workflow state. The current adapter maps broker statuses to `OrderStatus.PENDING`, `FILLED`, or `REJECTED`, but it does not model qualification-specific states such as `UNRESOLVED`, `RECONCILIATION_REQUIRED`, or `QUALIFIED`.

### PROPOSED V4.1 CHANGE

Keep broker lifecycle state separate from qualification workflow state. The qualification run should reference broker status and broker order identity, but broker order ID must never be the sole internal identity.

### CURRENT FACT — Simulator state is mutable local runtime state

- `broker/simulated.py:16-25` initializes a local JSON state path, defaulting to `state/simulated_broker.json`.
- `broker/simulated.py:35-51` loads or rewrites that file.
- `broker/simulated.py:72-93` appends accepted simulated orders and saves state.
- `broker/simulated.py:95-109` mutates order and position state for cancellation and reset.

### OBSERVED LIMITATION

Simulator state is useful operational state but is not immutable qualification evidence. A qualification design must not rely on the live simulator state file as the sole evidence of historical qualification.

### PROPOSED V4.1 CHANGE

Qualification evidence must be serialized as redacted, immutable artifacts with hashes. Mutable simulator or broker state may be referenced as observed state but not treated as frozen evidence unless copied to an immutable evidence artifact.

### CURRENT FACT — Alpaca Paper adapter is Paper-only by construction

- `broker/alpaca_paper.py:8-18` documents that the adapter has no live-mode switch and reads `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` from the environment.
- `broker/alpaca_paper.py:27-29` initializes `TradingClient(api_key, secret_key, paper=True)`.
- `broker/alpaca_paper.py:64-101` submits a Paper bracket order and returns a `BrokerOrder` with broker metadata.

### OBSERVED LIMITATION

The adapter enforces Paper mode, but there is no qualification-run state that proves endpoint checks, credential checks, operator approval, broker acknowledgment, cancellation, no-open-order checks, and no-position checks occurred in a single deterministic scenario.

### PROPOSED V4.1 CHANGE

Qualification must include Paper-environment guards and evidence, while keeping credentials redacted and live trading explicitly out of scope.

### CURRENT FACT — Submission service prevents preview/submission drift and duplicate immutable submissions

- `volcanoes/application/services/submit_trade.py:108-156` requires a shared `TradePlanner`, keeps process-local submitted and in-flight sets, and uses a lock.
- `volcanoes/application/services/submit_trade.py:157-173` records submission latency and counters.
- `volcanoes/application/services/submit_trade.py:198-285` recomputes the plan from a fresh `RiskPortfolioView`, compares the displayed expected plan, and emits `PlanDriftDetected` if material fields differ.
- `volcanoes/application/services/submit_trade.py:424-439` rejects duplicate submission of the same immutable request.

### OBSERVED LIMITATION

These safeguards are command-level and process-local. They do not create a durable qualification lifecycle, state revision, or restart recovery record.

### PROPOSED V4.1 CHANGE

The qualification state machine should define idempotency and state-revision rules now, with durable persistence deferred to V41-PQ-002.

### CURRENT FACT — Events exist, but publishing is not durable

- `volcanoes/events/models.py:34-120` defines immutable domain events including `TradePreviewed`, `TradeRejected`, `TradeSubmitted`, `TradeFilled`, `TradeCancelled`, `TradeFailed`, `PlanDriftDetected`, and `PolicyViolation`.
- `volcanoes/events/publisher.py:10-23` defines `EventPublisher` and `NullEventPublisher`; the null publisher validates event type but produces no external side effect.
- `volcanoes/application/operations/metrics.py:11-28` defines counters for previews, submissions, drift, idempotency, duplicate executions, scanner decisions, event publication attempts, and instrumentation failures.

### OBSERVED LIMITATION

The existing events and metrics are not a durable state-machine evidence ledger. They provide useful operational signals but no qualification-specific transition envelope, previous-evidence hash, state revision, or qualification-result record.

### PROPOSED V4.1 CHANGE

Define a qualification evidence envelope and minimum evidence set, while deferring durable event storage and publisher selection to approved implementation work.

### CURRENT FACT — Configuration and health reports already encode important safety boundaries

- `volcanoes/application/platform/configuration.py:90-100` rejects any concrete broker that is not explicitly Paper-only.
- `volcanoes/application/platform/configuration.py:112-116` requires manual preview and submission flags to move together.
- `volcanoes/application/platform/configuration.py:174-180` requires Alpaca Paper credentials before Alpaca Paper startup.
- `volcanoes/application/platform/health.py:91-113` reports active paths, rollback paths, persistence mode, process-local supervisor state, null-publisher limitation, non-transactional broker snapshots, and Paper-only long-only execution.

### OBSERVED LIMITATION

These startup checks and health messages are not equivalent to a completed Paper qualification run.

### PROPOSED V4.1 CHANGE

Qualification guards should reuse the same safety doctrine and must be visible in operator-facing qualification status.

## 9. Decision drivers

- Deterministic behavior.
- Explicit state visibility.
- No false completion.
- Broker acknowledgment distinct from broker execution.
- Duplicate prevention.
- Safe retries.
- Evidence for every material transition.
- Recovery from interruption.
- Reconciliation of uncertain states.
- Compatibility with existing v4.0 behavior.
- Testability.
- Minimal implementation complexity.
- Future persistence support.
- Future cross-process coordination.
- No premature distributed architecture.

## 10. Considered options

### Option A — Boolean qualification flag

Example: `qualified = true / false`.

This is rejected for v4.1 design because it cannot represent prechecks, approval, submission, broker acknowledgment, partial fill, cancellation, timeout, unresolved broker truth, recovery, evidence completeness, or negative scenarios that pass because the system rejected safely.

### Option B — Linear status field with unrestricted updates

Example: `status = "passed"`.

This is rejected because arbitrary assignment would allow invalid jumps such as `READY_FOR_APPROVAL` directly to `FILLED`, silent state corruption, duplicated broker requests, or false completion after an unresolved broker response.

### Option C — Explicit deterministic finite-state machine

This is the recommended working decision. States, transition rules, guards, side-effect intents, evidence, and failure behavior are explicit. The model is testable without a broker and can later be persisted without changing semantics.

### Option D — Event-sourced qualification lifecycle

Event sourcing has future value for replay, audit, and recovery. It is not selected for V41-PQ-001 because v4.1 needs the minimum sufficient design first. The state machine should emit evidence in a form that could support future event sourcing, but durable event-sourcing infrastructure is deferred.

## 11. Decision

Adopt an explicit deterministic finite-state machine for Paper qualification. The qualification state machine will coordinate, but not replace, the existing deterministic planner, submission service, broker adapter, event model, metrics, or operator approval flow.

The design uses coordinated state concerns rather than one overloaded status field:

1. Qualification workflow state: controls the qualification run.
2. Order lifecycle state: records broker-reported order progress.
3. Qualification result: records whether the scenario has passed, failed, aborted, or remains inconclusive.
4. Evidence state: records whether required transition evidence exists and is hash-verifiable.
5. Operator approval state: records explicit human authorization and its scope.

The qualification workflow may reference order lifecycle state, but `SUBMITTED`, `ACKNOWLEDGED`, `FILLED`, and `CANCELLED` are not automatically equal to `QUALIFIED`.

## 12. State model

### Proposed qualification workflow states

| State | Category | Meaning |
|---|---|---|
| `NOT_STARTED` | Initial | No qualification run has begun. |
| `PRECHECK_PENDING` | Active | Local and environment guards are being evaluated. |
| `PRECHECK_FAILED` | Recoverable failure | Prechecks failed; no broker request was sent. |
| `READY_FOR_APPROVAL` | Waiting | Preconditions passed and operator approval may be requested. |
| `APPROVAL_PENDING` | Waiting | Operator approval is being requested or displayed. |
| `APPROVED` | Active | Operator approval is recorded; no broker request has been sent yet. |
| `SUBMISSION_PENDING` | Active | The broker request is being prepared. |
| `SUBMITTED` | Externally uncertain | The request was sent; broker acknowledgment is not yet recorded. |
| `ACKNOWLEDGED` | Waiting | Broker acknowledged the order; fill/cancel/reject lifecycle remains open. |
| `PARTIALLY_FILLED` | Waiting | Broker reported a partial fill. |
| `FILLED` | Terminal order lifecycle | Broker reported full fill for scenarios requiring fill observation. |
| `CANCELLATION_REQUESTED` | Waiting | Cancellation was requested but not confirmed. |
| `CANCELLED` | Terminal order lifecycle | Broker confirmed cancellation. |
| `REJECTED` | Terminal order lifecycle or operator rejection | Broker, policy, configuration, or operator rejection occurred. |
| `EXPIRED` | Terminal order lifecycle | Broker reported expiration. |
| `UNRESOLVED` | Externally uncertain | Final broker state cannot be established. |
| `RECONCILIATION_REQUIRED` | Reconciliation required | Broker truth must be reconciled before continuing or finalizing. |
| `QUALIFIED` | Terminal success | Approved scenario criteria were completed with required evidence. |
| `DISQUALIFIED` | Terminal failure | Scenario criteria failed with evidence. |
| `ABORTED` | Terminal failure | Operator or system aborted before qualification criteria were met. |

### Separation of concerns

The model should be implemented as a qualification state machine referencing order lifecycle observations, not as a broker order state machine alone. Broker lifecycle states are facts reported by the broker; qualification states are system-governance states that decide whether the Paper path has satisfied an approved scenario.

## 13. Transition model

Transitions are listed formally in `docs/engineering/V41_PQ_001_TRANSITION_TABLE.md`.

Every transition must define source state, event or command, guard, destination state, side-effect intent, evidence event, idempotency behavior, retry classification, invalid-state behavior, operator-visible message, and qualification-result impact.

Arbitrary direct state assignment is prohibited.

## 14. Guard conditions

Guards are grouped as follows:

| Guard group | Examples | Classification |
|---|---|---|
| Environment | Paper environment only, supported broker adapter, live endpoint absent | Deterministic local and broker-dependent |
| Configuration | required flags, policy config valid, credential presence via approved secret path | Deterministic local |
| Broker capability | account reachable, order submission supported, cancellation supported, status retrieval supported | Broker-dependent |
| Trade plan | complete plan, quantity valid, price fields valid, risk-policy pass, deliberately non-marketable limit where scenario requires it | Deterministic local plus market-data freshness |
| Operator | explicit approval, rejection, emergency-stop inactive | Operator decision and local state |
| Evidence | evidence store available, transition envelope serializable, no secrets | Local implementation guard |
| Safety | no unresolved prior submission, no duplicate idempotency key, reconciliation complete where required | Local now, future persistence/coordination later |
| Scenario | scenario authorized and expected terminal criteria known | Deterministic local |

## 15. Idempotency

Material commands require idempotency keys. A repeated command with the same idempotency key and equivalent payload must return the recorded result without repeating external side effects. A repeated command using the same key with a materially different payload must fail deterministically.

Minimum idempotent commands:

- Start qualification.
- Request approval.
- Approve.
- Reject.
- Begin submission.
- Send broker request.
- Request cancellation.
- Reconcile.
- Finalize qualification.
- Abort.

Duplicate broker acknowledgments, duplicate fills, and duplicate cancellation confirmations must not duplicate state changes. Out-of-order, stale, or conflicting events must be rejected or moved to reconciliation according to the transition table.

## 16. Evidence and audit

Every material transition must produce qualification evidence. Proposed envelope fields:

- `evidence_id`.
- `occurred_at`.
- `recorded_at`.
- `qualification_run_id`.
- `qualification_scenario_id`.
- `correlation_id`.
- `event_type`.
- `source_state`.
- `destination_state`.
- `state_revision_before`.
- `state_revision_after`.
- `actor_type`.
- `actor_id`.
- `object_type`.
- `object_id`.
- `environment`.
- `broker`.
- `command_id`.
- `idempotency_key`.
- `result`.
- `reason_code`.
- `safe_message`.
- `broker_reference`.
- `payload_hash`.
- `previous_evidence_hash` where available.
- `application_version`.
- `schema_version`.

Evidence must not contain secrets, access tokens, credential values, authorization headers, account numbers, unnecessary balances, personal information, or unnecessary raw broker payloads.

Minimum evidence for qualification success:

- Qualification run created.
- Paper-only prechecks passed.
- Scenario selected and authorized.
- Trade plan or qualification order intent captured.
- Explicit operator approval captured.
- Broker request attempt captured.
- Broker acknowledgment or required broker lifecycle outcome captured.
- Cancellation, no-fill, no-open-order, and no-position checks captured when required by the scenario.
- Reconciliation evidence captured for any uncertain state.
- Final result captured with hash-verifiable evidence chain.

## 17. Failure handling

Failure categories and required behavior:

| Failure | State impact | Retry | Operator visibility | Evidence |
|---|---|---|---|---|
| Validation failure | `PRECHECK_FAILED` or `REJECTED` | Safe after correction | Plain reason | Required |
| Policy failure | `REJECTED` | Safe with new run/input | Explain policy | Required |
| Operator rejection | `REJECTED` | New run only | Explicit | Required |
| Configuration failure | `PRECHECK_FAILED` | Safe after correction | Blocked | Required |
| Authentication failure | `PRECHECK_FAILED` | Safe read retry after credential fix | Blocked | Redacted required |
| Authorization failure | `PRECHECK_FAILED` or `DISQUALIFIED` | After permission fix | Blocked | Redacted required |
| Broker transport failure before send | `PRECHECK_FAILED` or remain active | Safe local/read retry | Clear safe next step | Required |
| Broker transport failure after send | `UNRESOLVED` | No blind retry | Reconciliation required | Required |
| Broker rejection | `REJECTED` | Scenario-specific | Broker rejected | Required |
| Timeout | `UNRESOLVED` or `RECONCILIATION_REQUIRED` | Read/reconcile only | Reconciliation required | Required |
| Process interruption | Recovered from evidence/persistence | Depends on last durable state | Recovery status | Required in V41-PQ-002 |
| Persistence failure | Block consequential action | Not until evidence available | Evidence unavailable | Required if possible |
| Evidence-write failure | Block qualification finalization | Retry evidence write | Evidence unavailable | Required if possible |
| Inconsistent broker state | `RECONCILIATION_REQUIRED` | Reconcile only | State conflict | Required |
| Duplicate command | State unchanged or recorded replay | No external retry | Replay/conflict | Required |
| Stale event | State unchanged or reconciliation | No external retry | Stale event | Required |
| Unexpected event | State unchanged or reconciliation | No external retry | Unexpected event | Required |

If the application cannot establish whether the broker accepted an order, it must not retry blindly. It must move to `UNRESOLVED` or `RECONCILIATION_REQUIRED`, block consequential action for the same intent, record evidence, and require broker-state reconciliation.

## 18. Recovery and reconciliation

Recovery must be state- and evidence-driven. It must not rely solely on in-memory state.

Required recovery behavior:

- Restart before submission: resume from the last durable pre-submission state or abort safely if evidence is incomplete.
- Restart during submission: recover to `UNRESOLVED` unless durable evidence proves the broker request was not sent.
- Restart after broker acceptance but before local recording: require broker reconciliation using correlation, client order ID, broker order ID if known, symbol, side, quantity, and timestamps.
- Evidence interruption: block final qualification until evidence is available or mark result inconclusive.
- Network loss: use safe read/reconcile operations only.
- Broker outage: block consequential retry and record unresolved state.
- Delayed broker event: accept only if it matches run identity, revision expectations, and broker lifecycle order.
- Duplicate broker event: replay recorded result without changing state.
- Missing broker order ID: reconciliation required; do not qualify from local assumption.
- Unknown final broker state: `UNRESOLVED` or `RECONCILIATION_REQUIRED`, never `QUALIFIED`.

## 19. Persistence boundary

V41-PQ-001 defines the state machine. V41-PQ-002 remains the persistence implementation item.

This ADR defines persistence requirements only:

- Qualification state must be serializable.
- Qualification result must be serializable separately from workflow state.
- Evidence envelopes must be versioned.
- State must include a monotonic `state_revision` or equivalent concurrency token.
- State transitions should be committed atomically with evidence intent once persistence exists.
- Corruption must fail closed and require operator-visible recovery.
- In-memory implementation is acceptable for initial transition-function tests, but not for release qualification durability.

No database, queue, external event store, or durable infrastructure is selected by this ADR.

## 20. Concurrency boundary

V41-CP-001 remains the cross-process coordination item.

For V41-PQ-001:

- Single-process execution may use process-local locks.
- Concurrent mutation of the same qualification run is prohibited.
- Every command must carry an expected `state_revision` or equivalent stale-command guard once state is persisted.
- Stale commands must fail deterministically without side effects.
- Multi-process duplicate prevention, distributed locks, external queues, and cross-worker recovery are deferred.
- The design must not claim safety for multiple application processes against the same broker account until V41-CP-001 is implemented and accepted.

## 21. Operator-visible behavior

Operator-visible status must be calm, precise, and broker-truth preserving.

| State | Message |
|---|---|
| `NOT_STARTED` | Paper qualification has not started. |
| `PRECHECK_PENDING` | Qualification prechecks are running. No broker request has been sent. |
| `PRECHECK_FAILED` | Qualification prechecks did not pass. No broker request was sent. |
| `READY_FOR_APPROVAL` | Qualification is ready for operator approval. |
| `APPROVAL_PENDING` | Operator approval is required before any broker request. |
| `APPROVED` | Operator approval was recorded. No broker request has been sent yet. |
| `SUBMISSION_PENDING` | A broker request is being prepared. |
| `SUBMITTED` | The request was sent. Broker acknowledgment is pending. |
| `ACKNOWLEDGED` | The broker acknowledged the order. The order has not necessarily filled. |
| `PARTIALLY_FILLED` | The broker reported a partial fill. |
| `FILLED` | The broker reported the full fill. |
| `CANCELLATION_REQUESTED` | Cancellation was requested but has not yet been confirmed. |
| `CANCELLED` | The broker confirmed cancellation. |
| `REJECTED` | The request was rejected. No successful broker execution is assumed. |
| `EXPIRED` | The broker reported that the order expired. |
| `UNRESOLVED` | The final broker state cannot currently be confirmed. |
| `RECONCILIATION_REQUIRED` | Broker reconciliation is required before qualification can continue. |
| `QUALIFIED` | The approved Paper qualification criteria were completed successfully. |
| `DISQUALIFIED` | The qualification run did not meet the approved criteria. |
| `ABORTED` | Qualification was aborted. No further action will occur in this run. |

Avoid: completed when unresolved, successful when only submitted, safe trade, guaranteed, AI approved, or automatic approval language.

## 22. Security considerations

- Paper-only mode must be enforced before any broker action.
- Live endpoints must fail closed.
- Credentials must remain in approved secret paths and never appear in evidence, logs, exceptions, or operator screenshots.
- Evidence must redact broker payloads and account identifiers.
- Qualification artifacts must identify environment and broker without exposing account secrets.
- Operator-visible errors must be safe messages, not raw SDK exceptions containing sensitive content.

## 23. Testing consequences

Testing must prove the transition table, guards, idempotency, broker truth rules, evidence envelope, failure behavior, restart assumptions, and invariants. The implementation test plan is defined in `docs/engineering/V41_PQ_001_TEST_STRATEGY.md`.

## 24. Migration considerations

The first implementation should add qualification types and tests without changing existing v4.0 manual or scanner workflows. Existing preview/submission services may be composed by a qualification runner only after ADR approval. Rollback flags and existing deterministic execution must remain intact.

## 25. Rollback strategy

Until implementation begins, rollback means no code change. During a future implementation, the qualification feature must be feature-flagged or isolated so v4.0 deterministic preview/submission and scanner behavior can remain unchanged if qualification fails review.

## 26. Consequences

Positive consequences:

- Paper qualification becomes explicit, deterministic, reviewable, and testable.
- Broker acknowledgment is no longer conflated with qualification success.
- Unknown outcomes have safe states and reconciliation paths.
- Evidence requirements are known before implementation.
- Persistence and cross-process needs are identified without premature infrastructure.

Negative consequences:

- More states and tests are required than a boolean flag.
- Operators and developers must learn qualification-result semantics.
- Persistence and coordination gaps remain until their separate work items are implemented.

## 27. Risks

- Overloading one state field with broker, evidence, approval, and result semantics.
- Under-specifying evidence and making later persistence harder.
- Treating simulator state as immutable evidence.
- Retrying an uncertain broker submission and creating duplicates.
- Claiming Paper qualification after acknowledgment only when the scenario requires cancellation/no-fill proof.
- Implementing UI language that implies live-trading safety.

## 28. Deferred decisions

- Durable store selection for qualification runs.
- Evidence hash-chain implementation details.
- External event-publisher destination.
- Cross-process coordination mechanism.
- Exact timeout values and retry counts.
- Polling versus streaming broker status.
- Multi-user approval.
- Mobile submission.
- Live-trading qualification.
- Additional brokers.

## 29. Approval criteria

ADR-004 may be accepted only when:

- Current implementation findings are accurate.
- Qualification semantics are precise.
- States are minimal and sufficient.
- State ownership is clear.
- Qualification state is separated from broker lifecycle where appropriate.
- All allowed transitions are documented.
- Invalid transitions are documented.
- Idempotency is explicit.
- Broker truth is preserved.
- Unknown outcomes require reconciliation.
- Evidence requirements are complete.
- Restart expectations are defined.
- Persistence scope is deferred correctly to V41-PQ-002.
- Cross-process scope is deferred correctly to V41-CP-001.
- Testing strategy covers all transitions and invariants.
- Rollback is defined.
- No live-trading behavior is authorized.
- No implementation has occurred.
- Reviewers approve the design.

## 30. References

- `docs/vision/EMERS_CONSTITUTION.md`.
- `docs/vision/EMERS_PRODUCT_PRINCIPLES.md`.
- `docs/atlas/EMERS_PRODUCT_ARCHITECTURE.md`.
- `docs/atlas/EMERS_SECURITY_AND_TRUST_MODEL.md`.
- `docs/atlas/EMERS_BROKER_INTEGRATION_STRATEGY.md`.
- `docs/atlas/EMERS_DELIVERY_PHASES.md`.
- `docs/horizon/EMERS_CORE_USER_FLOWS.md`.
- `docs/horizon/EMERS_TRADE_APPROVAL_EXPERIENCE.md`.
- `docs/horizon/EMERS_BROKER_STATUS_EXPERIENCE.md`.
- `docs/horizon/EMERS_FAILURE_AND_DEGRADED_MODE_UX.md`.
- `docs/horizon/EMERS_CONTENT_AND_MICROCOPY_STANDARD.md`.
- `docs/roadmap/EDUTRADERAI_V4_1_ROADMAP.md`.
- `prototype/polaris/docs/POLARIS_INTERACTION_MAP.md`.
- `app.py`.
- `broker/base.py`.
- `broker/simulated.py`.
- `broker/alpaca_paper.py`.
- `adapters/paper_order_preview.py`.
- `adapters/paper_order_submission.py`.
- `adapters/paper_broker_execution.py`.
- `volcanoes/application/services/submit_trade.py`.
- `volcanoes/application/supervisor/supervisor.py`.
- `volcanoes/events/models.py`.
- `volcanoes/events/publisher.py`.
- `volcanoes/application/platform/configuration.py`.
- `volcanoes/application/platform/health.py`.
