# V41-PQ-001 Design: Paper Qualification State Machine

## 1. Purpose

Define the engineering design for a deterministic Paper-qualification state machine before production code changes. This document supports ADR-004 and remains design-only.

## 2. Scope

In scope:

- Qualification-run state model.
- Transition function shape.
- Guard model.
- Idempotency rules.
- Evidence-envelope requirements.
- Broker boundary requirements.
- Operator-approval boundary requirements.
- Initial implementation sequence forecast.

Out of scope until separately approved:

- Production Python implementation.
- Test-code changes.
- Broker behavior changes.
- Runtime configuration changes.
- Persistence backend selection.
- Cross-process coordination.
- Live trading.

## 3. Non-goals

- Do not replace `TradePlanner`, risk policies, sizing, or `ExecutionPipeline`.
- Do not add trading logic.
- Do not add scanner strategy behavior.
- Do not add a new broker.
- Do not infer live-trading readiness from Paper qualification.
- Do not select a database or event broker.

## 4. Current code map

| Area | Current file or symbol | Fact |
|---|---|---|
| Streamlit Paper Order UI | `app.py:441-515` | Calls deterministic preview/submission adapters and keeps operator confirmation. |
| Manual preview composition | `adapters/paper_order_preview.py:60-98` | Converts deterministic preview into legacy `RiskDecision` presentation shape. |
| Manual submission composition | `adapters/paper_order_submission.py:29-93` | Recomputes plan and calls `SubmitTradeService` when deterministic submission is enabled. |
| Root broker protocol | `broker/base.py:47-73` | Defines account, positions, open orders, submit, cancel, and close methods. |
| Local simulator | `broker/simulated.py:16-109` | Persists mutable runtime state to `state/simulated_broker.json`. |
| Alpaca Paper adapter | `broker/alpaca_paper.py:8-101` | Uses `TradingClient(..., paper=True)` and returns `BrokerOrder` metadata. |
| Volcanes broker adapter | `adapters/paper_broker_execution.py:13-57` | Rejects non-Paper brokers and maps broker status into Volcanes `Order`. |
| Execution pipeline | `volcanoes/execution/execution_pipeline.py:35-119` | Delegates planning to `TradePlanner`; submits approved plans through broker port. |
| Submission service | `volcanoes/application/services/submit_trade.py:108-173` | Shares planner, holds process-local duplicate sets, records metrics. |
| Drift prevention | `volcanoes/application/services/submit_trade.py:198-285` | Recomputes from fresh snapshot and rejects material plan drift. |
| Events | `volcanoes/events/models.py:34-120` | Immutable domain events for preview, rejection, submission, fills, cancellation, failure, drift, and policy violation. |
| Publisher | `volcanoes/events/publisher.py:10-23` | `NullEventPublisher` accepts event objects without durable side effect. |
| Configuration | `volcanoes/application/platform/configuration.py:90-180` | Validates Paper-only broker, feature-flag consistency, and Alpaca credential presence. |
| Health report | `volcanoes/application/platform/health.py:91-113` | Reports active paths, null publisher, process-local supervisor state, and limitations. |
| Operational metrics | `volcanoes/application/operations/metrics.py:11-28` | Defines fixed counters for observation, drift, idempotency, duplicates, scanner decisions, and instrumentation failures. |

## 5. Proposed domain model

Proposed conceptual types:

- `PaperQualificationRun`.
- `QualificationState`.
- `QualificationResult`.
- `QualificationCommand`.
- `QualificationEvent`.
- `TransitionDecision`.
- `TransitionError`.
- `QualificationScenario`.
- `QualificationEvidence`.
- `QualificationIdentifierSet`.

The model should use immutable data structures or controlled mutation through one authoritative transition mechanism. Direct writable state fields should not be exposed.

## 6. Proposed types

Pseudocode only:

```python
@dataclass(frozen=True, slots=True)
class PaperQualificationRun:
    qualification_run_id: str
    scenario_id: str
    state: QualificationState
    result: QualificationResult
    state_revision: int
    correlation_id: str
    idempotency_records: tuple[IdempotencyRecord, ...]
    identifiers: QualificationIdentifierSet
    evidence_head_hash: str | None
```

```python
class QualificationState(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    PRECHECK_PENDING = "PRECHECK_PENDING"
    READY_FOR_APPROVAL = "READY_FOR_APPROVAL"
    APPROVED = "APPROVED"
    SUBMISSION_PENDING = "SUBMISSION_PENDING"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    QUALIFIED = "QUALIFIED"
    DISQUALIFIED = "DISQUALIFIED"
```

The full state list is defined in ADR-004 and the transition table.

## 7. Proposed state representation

State representation should include:

- `qualification_run_id`.
- `qualification_scenario_id`.
- `state`.
- `result`.
- `state_revision`.
- `created_at`.
- `updated_at`.
- `correlation_id`.
- Current operator approval reference.
- Current internal order reference.
- Broker reference if known.
- Last evidence hash.
- Last safe message.
- Reconciliation requirement flag and reason.

## 8. Proposed event representation

Qualification events should be separate from current trade events, while preserving common correlation IDs and redaction rules. Examples:

- `QualificationStarted`.
- `PrechecksPassed`.
- `PrechecksFailed`.
- `ApprovalRequested`.
- `OperatorApproved`.
- `OperatorRejected`.
- `SubmissionStarted`.
- `BrokerRequestSent`.
- `BrokerAcknowledged`.
- `BrokerPartialFillReported`.
- `BrokerFillReported`.
- `CancellationRequested`.
- `BrokerCancellationConfirmed`.
- `BrokerRejected`.
- `SubmissionTimeoutUnresolved`.
- `ReconciliationStarted`.
- `ReconciliationResolved`.
- `QualificationPassed`.
- `QualificationDisqualified`.
- `QualificationAborted`.

## 9. Proposed transition function

Pseudocode:

```python
def transition(
    current_state: PaperQualificationRun,
    event: QualificationEvent,
    context: QualificationContext,
) -> TransitionDecision:
    ...
```

`TransitionDecision` should contain:

- accepted or rejected.
- previous state.
- next state.
- reason code.
- safe explanation.
- required side-effect intents.
- evidence intent.
- retry classification.
- result impact.
- next state revision.

The transition function should be pure or near-pure. External side effects must not occur inside untestable state mutation.

## 10. Proposed command handling

Separate command handling into four phases:

1. Validate command, expected state, and expected revision.
2. Resolve idempotency.
3. Ask transition function for a decision and side-effect intents.
4. Execute authorized side effects outside the pure transition function, then record broker outcome and evidence.

Conceptual public operations:

- `start_qualification(...)`.
- `record_precheck_result(...)`.
- `request_approval(...)`.
- `approve(...)`.
- `reject(...)`.
- `begin_submission(...)`.
- `record_submission_attempt(...)`.
- `record_broker_acknowledgment(...)`.
- `record_partial_fill(...)`.
- `record_fill(...)`.
- `request_cancellation(...)`.
- `record_cancellation(...)`.
- `record_broker_rejection(...)`.
- `mark_unresolved(...)`.
- `require_reconciliation(...)`.
- `record_reconciliation(...)`.
- `finalize_qualification(...)`.
- `abort(...)`.

Names should be finalized only when implementation starts and repository conventions are reviewed again.

## 11. Proposed error types

- `InvalidTransitionError`.
- `GuardConditionError`.
- `DuplicateCommandError`.
- `IdempotencyConflictError`.
- `StaleRevisionError`.
- `QualificationTerminalError`.
- `EvidenceUnavailableError`.
- `BrokerStateUnresolvedError`.
- `ReconciliationRequiredError`.
- `UnsupportedScenarioError`.

Errors must expose safe messages only and must not include credentials, headers, raw secrets, account numbers, or unnecessary broker payloads.

## 12. Proposed evidence integration

The transition function should produce an evidence intent. A later persistence/evidence layer records the envelope and returns the evidence ID and hash. Until V41-PQ-002, tests may use an in-memory fake evidence sink.

Evidence commitment should eventually be ordered so that consequential side effects are reconstructable. The design should not claim transactional guarantees until persistence exists.

## 13. Proposed broker boundary

The qualification state machine must not import concrete broker adapters. A qualification runner may use a narrow outer adapter that can:

- Confirm Paper mode.
- Retrieve account/position/open-order status.
- Submit the approved qualification order when authorized.
- Retrieve broker order status.
- Request cancellation when authorized.
- Confirm cancellation/no-open-order/no-position.

It must not recalculate quantity, risk, policy approval, or sizing.

## 14. Proposed approval boundary

Operator approval must be represented as a state-machine event with explicit scope:

- Scenario ID.
- Qualification run ID.
- Symbol.
- Side.
- Quantity.
- Order type.
- Limit price.
- Broker mode.
- Expiration or validity condition.
- Correlation ID.

A stale or modified plan invalidates approval and requires a new event.

## 15. Proposed qualification runner

The runner coordinates existing services and new state-machine decisions:

```text
Operator or release tool
  -> QualificationRunner
  -> QualificationStateMachine
  -> existing planner/submission/broker ports where authorized
  -> evidence sink
```

The runner should call the deterministic services but should not duplicate sizing, policy checks, or order-construction logic.

## 16. Proposed public API

A future application service may expose:

```python
start_qualification(command) -> QualificationResultView
approve_qualification(command) -> QualificationResultView
submit_qualification(command) -> QualificationResultView
record_broker_status(command) -> QualificationResultView
reconcile_qualification(command) -> QualificationResultView
finalize_qualification(command) -> QualificationResultView
```

The API should return presentation-neutral result views that include state, result, safe message, required next action, evidence references, and correlation ID.

## 17. Serialization requirements

Serializable state must be deterministic and versioned:

- No object references to Streamlit, SDK clients, broker clients, or credentials.
- Decimal and timestamp formats must be stable.
- Enums must serialize as explicit strings.
- Evidence payloads must be sorted where hashes depend on JSON serialization.
- Schema version must be included.

## 18. Concurrency expectations

V41-PQ-001 should require:

- Single-writer mutation per qualification run.
- Monotonic `state_revision`.
- Expected-revision checks on commands.
- Deterministic stale-command rejection.
- Process-local locks acceptable only for initial implementation.

V41-CP-001 must decide multi-process coordination.

## 19. Observability

Metrics to design for:

- State-transition count by transition ID.
- Invalid-transition count.
- Guard-failure count.
- Unresolved-state count.
- Reconciliation count.
- Duplicate-command count.
- Qualification duration.
- Terminal result.
- Broker-outcome category.
- Evidence-write failure count.

No new observability dependency is selected here.

## 20. Security

- Qualification must fail closed on live endpoints.
- Evidence must be redacted.
- Credential presence may be recorded; credential values may not.
- Broker account numbers, balances, and personal information should not be included unless strictly required and redacted.
- Raw SDK exceptions should be mapped to safe errors.

## 21. Migration path

1. Accept ADR-004 after review.
2. Add state-machine enums, contracts, and transition function behind tests.
3. Add in-memory evidence sink/fakes for deterministic tests.
4. Add qualification runner composition without changing existing manual or scanner paths.
5. Add Paper-only qualification workflow behind an explicit flag or command.
6. Add V41-PQ-002 persistence before claiming restart-durable qualification.
7. Add V41-CP-001 coordination before claiming multi-process qualification safety.

## 22. Implementation sequence

Recommended sequence after ADR approval:

1. `volcanoes/application/qualification/contracts.py`.
2. `volcanoes/application/qualification/state_machine.py`.
3. `volcanoes/application/qualification/evidence.py` interface.
4. `volcanoes/application/qualification/runner.py`.
5. Adapter-level Paper broker qualification bridge.
6. Release-tool or admin command integration.
7. Evidence manifest integration.
8. Documentation update from Proposed to Accepted only after review.

## 23. File-change forecast

Potential future files:

- `volcanoes/application/qualification/__init__.py`.
- `volcanoes/application/qualification/contracts.py`.
- `volcanoes/application/qualification/state_machine.py`.
- `volcanoes/application/qualification/runner.py`.
- `volcanoes/application/qualification/evidence.py`.
- `adapters/paper_qualification_broker.py`.
- `scripts/run_paper_qualification.py` or a release-safe equivalent.
- `tests/test_paper_qualification_state_machine.py`.
- `tests/test_paper_qualification_runner.py`.
- `tests/test_paper_qualification_evidence.py`.

This forecast is not authorization to implement.

## 24. Test impact forecast

Future tests should cover transition rows, invalid transitions, guard failures, idempotency, duplicate broker events, out-of-order events, evidence serialization, no-secret payloads, restart recovery, broker-boundary behavior, and architecture boundaries.

## 25. Rollback

Before production integration, rollback is simply not enabling the feature. Once implemented, qualification must remain isolated so existing deterministic preview, deterministic submission, supervised scanner behavior, and v4.0 rollback flags remain untouched.

## 26. Open questions

- What exact qualification scenarios are required for v4.1 release readiness?
- What evidence sink will V41-PQ-002 select?
- Should the qualification runner live under application services or a new qualification package?
- What exact timeout values should be used, and where should they be configured?
- Should the first implementation include an admin CLI, Streamlit admin panel, or release-script entry point?
- How should Alpaca client order IDs encode qualification-run identity without leaking sensitive data?



## V41-PQ-001A implementation mapping

The first implementation slice maps the design to these files:

- `volcanoes/application/qualification/contracts.py` contains immutable state, result, event, context, decision, side-effect intent, evidence intent, guard, and transition-spec contracts.
- `volcanoes/application/qualification/errors.py` contains typed transition errors with stable reason codes and safe messages.
- `volcanoes/application/qualification/state_machine.py` contains the deterministic transition registry and pure transition-evaluation function.
- `tests/test_paper_qualification_state_machine.py` contains the focused unit and invariant test suite for V41-PQ-001A.

This mapping does not change the accepted architecture and does not implement broker execution, persistence, event publication, runtime composition, UI, CLI, or cross-process coordination.

## Sentinel correction: side-effect boundary contract

The implementation must split command processing into these explicit records:

1. Command validation result.
2. Idempotency lookup or reservation.
3. Transition decision.
4. Pre-effect evidence intent.
5. External side-effect attempt, only when authorized.
6. Post-effect broker observation or unresolved marker.
7. State commitment.
8. Evidence commitment.

V41-PQ-001 may implement this with in-memory fakes for tests, but it must not claim restart durability. If the process cannot prove whether an external request crossed the broker boundary, the runner must reconstruct through read-only reconciliation rather than replaying the external command.

## Sentinel correction: mandatory scenario selection

The initial implementation should target PQ-SCN-005 as the mandatory positive Paper-qualification scenario: one-share, Paper-only, deliberately non-marketable order, explicit approval, one broker submission, broker acknowledgment/status capture, zero-fill observation, cancellation request, broker cancellation confirmation, no-open-order check, no-position check, redacted evidence, and final `QUALIFIED` only after all scenario criteria are present.

## 27. Approval gate

Implementation may begin only after ADR-004 is reviewed and accepted. Approval must confirm that the design preserves Paper-only scope, explicit operator approval, broker truth, evidence requirements, idempotency, reconciliation, and the deferred boundaries for persistence and cross-process coordination.
