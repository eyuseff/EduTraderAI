# V41-PQ-001F5D1 Implementation Report: Paper Execution Lifecycle Core

## 1. Status

V41-PQ-001F5D1 is implemented as a pure deterministic lifecycle core.

## 2. Scope implemented

Implemented:

- Accepted ADR-006 22-state Paper execution lifecycle enum.
- Accepted 30-transition `PX-TRN-001` through `PX-TRN-030` table.
- Immutable lifecycle aggregate.
- Immutable lifecycle input contract.
- Immutable transition context.
- Immutable transition specification.
- Immutable transition decision.
- Immutable descriptive side-effect intents.
- Immutable descriptive evidence intents.
- Pure transition function.
- Pure apply-transition function.
- Expected-revision validation.
- Identity validation for aggregate and correlation IDs.
- Deterministic command replay classification.
- Duplicate-command conflict classification.
- Idempotency replay and conflict classification.
- Duplicate broker-observation replay classification.
- Conflicting broker-observation classification.
- Unknown-outcome and reconciliation-required behavior.
- Cancellation and replacement guards.
- Partial-fill monotonicity and final-fill guards.
- Typed lifecycle error vocabulary.

## 3. Files added

- `volcanoes/application/execution/lifecycle/__init__.py`
- `volcanoes/application/execution/lifecycle/contracts.py`
- `volcanoes/application/execution/lifecycle/enums.py`
- `volcanoes/application/execution/lifecycle/errors.py`
- `volcanoes/application/execution/lifecycle/state_machine.py`
- `volcanoes/application/execution/lifecycle/transition_table.py`
- `tests/test_paper_execution_lifecycle.py`

## 4. Files updated

- `volcanoes/application/execution/__init__.py`
- `tests/test_architecture_dependencies.py`
- `docs/engineering/V41_PQ_001_DESIGN.md`
- `docs/roadmap/EDUTRADERAI_V4_1_ROADMAP.md`

## 5. State model

The implementation encodes exactly these accepted states:

`CREATED`, `ELIGIBILITY_EVALUATED`, `INELIGIBLE`,
`APPROVAL_CONFIRMED`, `IDEMPOTENCY_RESERVED`,
`READY_FOR_DISPATCH`, `DISPATCH_PENDING`, `DISPATCHED`,
`BROKER_ACKNOWLEDGED`, `PARTIALLY_FILLED`, `FILLED`,
`CANCEL_REQUESTED`, `CANCEL_PENDING`, `CANCELLED`,
`REPLACE_REQUESTED`, `REPLACE_PENDING`, `REPLACED`,
`BROKER_REJECTED`, `OUTCOME_UNKNOWN`,
`RECONCILIATION_REQUIRED`, `FAILED_TERMINAL`,
and `ABORTED_BEFORE_DISPATCH`.

The implementation intentionally does not introduce `ELIGIBLE`, `RECOVERED`,
`DRY_RUN_ACCEPTED`, `DRY_RUN_REJECTED`, `WORKING`, or Live states.

## 6. Transition model

The implementation encodes exactly 30 accepted transition specifications:
`PX-TRN-001` through `PX-TRN-030`.

Accepted transitions increment `PaperExecutionRevision` exactly once. Rejected
transitions, stale revision checks, replays, command conflicts, idempotency
conflicts, and broker-observation conflicts do not increment revision.

## 7. Replay and conflict behavior

The transition function models:

- command replay;
- command conflict;
- idempotency replay;
- idempotency conflict;
- broker-observation replay;
- broker-observation conflict.

All replay and conflict outcomes are deterministic decisions with descriptive
evidence intents only. They do not execute, persist, or contact anything.

## 8. Unknown outcome and reconciliation

`OUTCOME_UNKNOWN` is restricted to reconciliation entry or terminal failure.
`RECONCILIATION_REQUIRED` accepts only reconciliation result or terminal
failure. Reconciliation destinations are bounded and deterministic.

## 9. Fill, cancellation, and replacement safety

Partial-fill observations must be monotonic and below requested quantity when
the requested quantity is known. Final-fill observations must equal requested
quantity when the requested quantity is known.

Cancellation request is not cancellation. Replacement request is not
replacement. Replacement cannot move quantity below already-filled quantity.

## 10. Side-effect boundary

The lifecycle core emits descriptive side-effect intents such as
`WOULD_DISPATCH`, `WOULD_REQUEST_CANCEL`, and `WOULD_RECONCILE`.

These are inert labels only. F5D1 implements no executor, no dry-run executor,
no broker port, no broker adapter, no broker call, no persistence, no
configuration change, and no runtime wiring.

## 11. Evidence boundary

The lifecycle core emits descriptive evidence intents such as
`LIFECYCLE_TRANSITION_ACCEPTED`, `LIFECYCLE_REPLAYED`,
`LIFECYCLE_BROKER_OBSERVATION_CONFLICT`, and
`LIFECYCLE_RECONCILIATION_REQUIRED`.

F5D1 does not persist evidence and does not publish events.

## 12. Architecture guardrails

Architecture tests now enforce that the lifecycle package:

- imports no broker, adapter, scanner, engine, persistence, network, logging,
  event, operations, supervisor, qualification, or eligibility dependencies;
- contains no executor, broker-port, persistence-port, or dry-run-executor
  classes;
- contains no runtime side-effect tokens;
- contains no Live or rejected dry-run state symbols;
- is not wired into current runtime entry points.

## 13. Verification summary

Focused lifecycle tests:

- `tests/test_paper_execution_lifecycle.py`: 214 passed.

Architecture tests:

- `tests/test_architecture_dependencies.py`: 71 passed.

Full verification is required before commit.

## 14. Deferred work

Deferred to later slices:

- V41-PQ-001F5D2 deterministic dry-run executor.
- Real executor.
- Broker port.
- Broker adapter.
- Persistence.
- Durable idempotency.
- Runtime wiring.
- Simulator integration.
- Scanner integration.
- Live behavior.

## 15. Disposition

F5D1 satisfies the accepted pure lifecycle-core scope. The next recommended
implementation slice remains V41-PQ-001F5D2, and it must not bypass the
lifecycle boundary or introduce broker side effects without a separately
approved scope.
