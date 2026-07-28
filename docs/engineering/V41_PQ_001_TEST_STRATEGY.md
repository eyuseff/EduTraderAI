# V41-PQ-001 Test Strategy

## 1. Purpose

Define the test strategy for the Paper-qualification state machine before implementation. This document is design-only and adds no tests in this phase.

## 2. Test objectives

- Prove every allowed transition behaves deterministically.
- Prove invalid transitions preserve state and produce no side-effect intent.
- Prove approval cannot be bypassed.
- Prove broker acknowledgment is not treated as fill or qualification unless scenario criteria allow it.
- Prove unresolved outcomes require reconciliation.
- Prove evidence requirements are enforced.
- Prove idempotency prevents duplicate external side effects.
- Prove state revision increases monotonically.
- Prove no secrets appear in evidence or errors.

## 3. Test levels

| Level | Purpose |
|---|---|
| Unit | Pure transition function, guards, error types, serialization helpers. |
| Contract | Broker boundary, evidence sink, idempotency store, operator approval boundary. |
| Integration | Qualification runner with fake broker and fake evidence sink. |
| Recovery | Restart and reconciliation from serialized state/evidence. |
| Architecture | Dependency boundaries and no concrete broker/Streamlit imports in core qualification code. |
| Acceptance | Required qualification scenarios with controlled fake brokers and redacted evidence. |

## 4. Unit-test strategy

Unit tests should instantiate immutable run state, event/command objects, and context objects, then call the transition function directly. They should assert decision acceptance, next state, result impact, side-effect intents, evidence intent, safe messages, and state revision behavior.

## 5. Transition-table tests

Every row in `docs/engineering/V41_PQ_001_TRANSITION_TABLE.md` should have:

- Positive test.
- Invalid-source test.
- Guard-failure test.
- Duplicate-event test where relevant.
- Evidence assertion.
- State-revision assertion.
- Side-effect-intent assertion.
- Operator-message assertion where relevant.

## 6. Property/invariant tests

Core invariants:

- Every accepted transition has an allowed source/event pair.
- Every rejected transition leaves state unchanged.
- No external side effect occurs for rejected transitions.
- Terminal states reject mutation unless explicitly allowed for a new qualification run.
- Qualification cannot pass without required evidence.
- Approval cannot be bypassed.
- Submission cannot occur twice for the same idempotency key.
- Cancellation cannot become confirmed without broker confirmation.
- Unresolved cannot become passed without reconciliation.
- Duplicate broker events do not duplicate state changes.
- Out-of-order broker events are rejected or reconciled deterministically.
- State revision increases monotonically.
- Result and workflow state remain logically consistent.
- No secrets appear in evidence or exceptions.
- Identical input produces identical transition decisions.

## 7. Guard tests

Guard tests should cover:

- Paper environment only.
- Live endpoint fails closed.
- Supported broker adapter.
- Missing credentials.
- Invalid broker configuration.
- Market-data freshness where required.
- Trade-plan completeness.
- Risk-policy pass/fail.
- Explicit operator approval.
- Emergency stop active.
- Unresolved prior submission.
- Duplicate idempotency key.
- Invalid quantity.
- Invalid prices.
- Missing evidence sink.
- Unsupported broker capability.
- Reconciliation incomplete.
- Unauthorized scenario.

## 8. Idempotency tests

Required cases:

- Repeated identical `START_QUALIFICATION` returns the same run.
- Repeated approval returns recorded approval and does not create a new authorization.
- Repeated submission command after broker request does not send a second request.
- Same idempotency key with changed payload fails deterministically.
- Duplicate broker acknowledgment is replayed.
- Duplicate fill does not increment filled quantity twice.
- Duplicate cancellation confirmation is replayed.
- Timeout after submission blocks blind retry.
- Restarted command with known durable record returns recorded result.

## 9. Failure tests

Failure categories to test:

- Validation failure.
- Policy failure.
- Operator rejection.
- Configuration failure.
- Authentication failure.
- Authorization failure.
- Broker transport failure before send.
- Broker transport failure after send.
- Broker rejection.
- Timeout.
- Process interruption.
- Persistence failure for future V41-PQ-002.
- Evidence-write failure.
- Inconsistent broker state.
- Duplicate command.
- Stale event.
- Unexpected event.
- Reconciliation failure.

## 10. Recovery tests

Recovery tests should simulate:

- Application restart before submission.
- Process crash during submission.
- Process crash after broker acceptance but before local recording.
- Evidence-store interruption.
- Network loss.
- Broker outage.
- Delayed broker event.
- Duplicate broker event.
- Missing broker order ID.
- Unknown final broker state.

## 11. Broker-boundary tests

Use controlled fake brokers. Do not use live Alpaca in automated tests.

Required assertions:

- Qualification core imports no concrete broker adapter.
- Fake broker receives no submission before approval.
- Approved scenario sends exactly one broker request.
- Submitted symbol, side, quantity, order type, limit price, stop, and target match the approved plan or qualification order spec.
- Rejection maps to broker lifecycle state without claiming qualification success unless scenario is a rejection scenario.
- Cancellation request and confirmation are separate.
- Unknown broker response moves to unresolved/reconciliation.

## 12. Evidence tests

- Every accepted transition emits evidence intent.
- Invalid transition emits diagnostic evidence where possible.
- Evidence includes qualification run ID, scenario ID, correlation ID, transition ID, source/destination state, state revision, idempotency key, result, safe message, payload hash, schema version, and application version.
- Evidence excludes secrets, credentials, authorization headers, account numbers, and unnecessary raw broker payloads.
- Evidence serialization is deterministic.
- Evidence hash changes when material payload changes.
- Previous evidence hash links where supported.

## 13. Restart tests

Restart tests should load serialized state and evidence. They should assert:

- Hash match resumes safely.
- Missing evidence blocks qualification finalization.
- Corrupt evidence fails closed.
- Unknown broker side effect moves to reconciliation.
- Stale revision fails deterministically.

## 14. Concurrency tests

Within V41-PQ-001 scope:

- Process-local concurrent commands for the same run serialize.
- Stale revision rejects.
- Same idempotency key and same payload replays.
- Same idempotency key and different payload conflicts.
- Concurrent submission attempts produce one side-effect intent.

Cross-process tests are deferred to V41-CP-001.

## 15. Scenario tests

| Scenario | Purpose | Expected final state | Qualification result |
|---|---|---|---|
| PQ-SCN-001 | Approved order acknowledged | `QUALIFIED` if ack-only scenario | `PASSED` |
| PQ-SCN-002 | Approved order partially filled | Scenario-dependent | `PASSED`, `FAILED`, or `INCONCLUSIVE` by criteria |
| PQ-SCN-003 | Approved order fully filled | `QUALIFIED` for fill scenario | `PASSED` |
| PQ-SCN-004 | Broker rejection | `QUALIFIED` for rejection-handling scenario, otherwise `DISQUALIFIED` | Scenario-dependent |
| PQ-SCN-005 | Cancellation requested and confirmed | `QUALIFIED` for cancellation/no-fill scenario | `PASSED` |
| PQ-SCN-006 | Submission timeout with later reconciliation | `QUALIFIED`, `DISQUALIFIED`, or `RECONCILIATION_REQUIRED` | Depends on reconciliation |
| PQ-SCN-007 | Duplicate submission command | Existing terminal or active state unchanged | No duplicate side effect |
| PQ-SCN-008 | Operator rejection before submission | `QUALIFIED` for rejection scenario or `REJECTED` | Scenario-dependent |
| PQ-SCN-009 | Precheck failure | `PRECHECK_FAILED` or `DISQUALIFIED` | `FAILED` or `INCONCLUSIVE` |
| PQ-SCN-010 | Process restart during active qualification | Recovered state or `RECONCILIATION_REQUIRED` | `PENDING` or `INCONCLUSIVE` |
| PQ-SCN-011 | Unknown broker state | `UNRESOLVED` or `RECONCILIATION_REQUIRED` | `INCONCLUSIVE` |
| PQ-SCN-012 | Evidence write failure | Consequential action blocked or finalization blocked | `INCONCLUSIVE` or `FAILED` |

Mandatory v4.1 success scenario should be selected during ADR review. The roadmap currently points to a Paper-only one-share non-marketable qualification that submits exactly one order, captures broker acknowledgment/status, verifies zero fill, cancels, confirms no open orders and no position, and emits redacted immutable evidence.

## 16. Regression tests

Regression tests should preserve v4.0 behavior:

- Manual deterministic preview still works.
- Manual deterministic submission still uses shared planner.
- Plan drift still rejects before broker submission.
- Supervised scanner behavior remains unchanged unless explicitly integrated later.
- Rollback flags retain existing behavior.
- Architecture dependency tests remain green.

## 17. Coverage expectations

State-machine unit tests should target exhaustive branch coverage for transition decisions. Integration and recovery tests should cover every mandatory scenario and every failure category. Coverage should not be inflated with unjustified exclusions.

## 18. Determinism requirements

- Same state, event, and context produce same transition decision.
- Clocks and ID generators must be injectable in tests.
- Serialization order must be stable.
- Fake brokers must be controlled fixtures.
- No external network calls in automated tests.

## 19. Test-data rules

- Use fake credentials and fake broker identifiers only.
- Use simulated or fake account data only.
- Do not print secrets.
- Do not use live Alpaca in automated tests.
- Keep qualification evidence fixtures redacted and deterministic.

## 20. Acceptance criteria

Implementation acceptance requires:

- All transition rows tested.
- All invariants tested.
- All mandatory qualification scenarios tested.
- No unauthorized imports in qualification core.
- No live endpoint path reachable.
- No broker submission before approval.
- Exactly one broker request for approved qualification submission.
- No duplicate external side effect on replay.
- Unknown broker outcomes require reconciliation.
- Evidence is deterministic, redacted, and complete.
- Existing v4.0 tests remain green.

## 21. Deferred tests

Deferred to V41-PQ-002:

- Durable database corruption behavior.
- Real restart from production persistence.
- Evidence store migration.

Deferred to V41-CP-001:

- Multi-process lock behavior.
- Distributed idempotency.
- Cross-worker stale command handling.

Deferred to broker smoke procedure:

- Credentialed Alpaca Paper smoke using real credentials.

## 22. Implementation test sequence

1. Enum and contract validation tests.
2. Pure transition function tests.
3. Invalid transition and guard tests.
4. Idempotency tests.
5. Evidence serialization tests.
6. Fake broker boundary tests.
7. Qualification runner scenario tests.
8. Recovery/restart tests with fake persistence.
9. Architecture dependency tests.
10. Full verification suite.
