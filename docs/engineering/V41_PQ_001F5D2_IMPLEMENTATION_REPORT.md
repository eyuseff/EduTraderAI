# V41-PQ-001F5D2 Implementation Report: Deterministic Paper Dry-Run Executor

## 1. Executive summary

V41-PQ-001F5D2 implements a deterministic, side-effect-free Paper dry-run
executor. It composes existing F5B execution contracts, F5C eligibility, and
F5D1 lifecycle transitions to answer what orchestration would do with explicit
immutable facts.

## 2. Starting baseline

Starting HEAD: `2346e32fe3c4563a8a9982185204c3493f3d8402`.

Baseline included F5B contracts, F5C eligibility, F5D1 lifecycle core, 1,558
passing tests, 71 architecture tests, and 85.5% coverage.

## 3. Scope implemented

- `PaperDryRunExecutor`
- `PaperDryRunRequest`
- `PaperDryRunResult`
- `PaperDryRunDecision`
- `PaperDryRunOutcomeKind`
- `PaperDryRunStep`
- `PaperDryRunStepKind`
- `PaperDryRunFailure`
- `PaperDryRunReceipt`
- `PaperExecutionEffectMode`

## 4. Scope excluded

No broker port, broker adapter, broker call, simulator access, persistence,
durable idempotency, runtime wiring, readiness authority, event publisher,
metrics, logging, UI, API, CLI, dependency, configuration, or Live behavior was
added.

## 5. ADR-005 and ADR-006 conformance

ADR-005 remains Paper-only. ADR-006 remains the lifecycle authority. F5D2 does
not alter lifecycle semantics and does not enter broker-truth states during a
successful dry run.

## 6. Package structure

`volcanoes/application/execution/dry_run/` contains:

- `__init__.py`
- `contracts.py`
- `enums.py`
- `errors.py`
- `executor.py`

## 7. Public API

Primary API:

```python
PaperDryRunExecutor.execute(request: PaperDryRunRequest) -> PaperDryRunResult
```

The method name is scoped to a dry-run executor. Results always encode
`action_executed=False`.

## 8. Effect-mode model

`PaperExecutionEffectMode` contains exactly one value: `DRY_RUN`.

Paper environment remains represented by `PaperExecutionMode.PAPER`.

## 9. Request model

`PaperDryRunRequest` contains an immutable command, eligibility policy,
explicit evaluation timestamp, caller-supplied initial lifecycle, explicit
lifecycle guard facts, optional prior result, and a deterministic `pdr-`
fingerprint.

## 10. Result model

`PaperDryRunResult` contains outcome, request fingerprint, command identity,
aggregate identity, correlation identity, eligibility result, initial/final
lifecycle, ordered steps, receipt or failure, transition IDs, revision trace,
replay/external-evidence/reconciliation flags, safety booleans, and a
deterministic `pdo-` fingerprint.

## 11. Decision model

Supported outcomes:

- `WOULD_DISPATCH`
- `WOULD_REJECT`
- `WOULD_REQUIRE_EXTERNAL_EVIDENCE`
- `WOULD_REQUIRE_RECONCILIATION`
- `NO_ACTION_REPLAY`

## 12. Step model

Steps are immutable and ordered. Step kinds include request validation,
eligibility evaluation, lifecycle eligibility recording, approval recording,
simulated idempotency reservation, ready-for-dispatch, replay, failed-safe, and
would-dispatch/reconciliation markers.

## 13. Receipt model

`PaperDryRunReceipt` is dedicated to dry run and uses `pdt-` fingerprints. It
does not manufacture broker references or broker receipt kinds.

## 14. Failure model

`PaperDryRunFailure` is immutable, normalized, safe, and uses `pdf-`
fingerprints. Ordinary rejection returns a failure result rather than raising.

## 15. Eligibility composition

The executor uses `PaperExecutionEligibilityService` as the sole eligibility
evaluator. It invokes eligibility exactly once for non-replayed requests and
does not reproduce eligibility logic.

## 16. Lifecycle composition

The executor uses F5D1 `transition(...)` and `apply_transition(...)` as the sole
lifecycle authority.

## 17. Successful dry-run path

Successful `SUBMIT` dry run follows:

`CREATED -> ELIGIBILITY_EVALUATED -> APPROVAL_CONFIRMED ->
IDEMPOTENCY_RESERVED -> READY_FOR_DISPATCH`

The result is `WOULD_DISPATCH`.

## 18. Ineligible path

`INELIGIBLE` eligibility returns `WOULD_REJECT`. When the supplied lifecycle can
accept `RECORD_INELIGIBLE`, the terminal lifecycle transition is recorded.

## 19. Indeterminate path

`INDETERMINATE` eligibility returns `WOULD_REQUIRE_EXTERNAL_EVIDENCE` and
preserves unresolved external-evidence semantics.

## 20. Approval handling

The executor never creates approval. It relies on F5B approval evidence and F5C
approval checks. Invalid, unbound, not-yet-valid, or expired approval produces a
dry-run rejection.

## 21. Simulated reservation handling

The executor only consumes caller-supplied immutable reservation facts.
`idempotency_reservation_confirmed=True` permits dry-run lifecycle progression;
false fails safely. No durable reservation is made.

## 22. Replay behavior

An exact prior-result replay returns `NO_ACTION_REPLAY`, does not invoke
eligibility again, does not advance lifecycle revision, and does not duplicate
consequential intents. Same command with a different request fingerprint
returns deterministic conflict.

## 23. Revision behavior

Accepted lifecycle transitions increment revision only through F5D1. Dry-run
orchestration does not independently modify revisions.

## 24. Reconciliation handling

Initial `OUTCOME_UNKNOWN` or `RECONCILIATION_REQUIRED` returns
`WOULD_REQUIRE_RECONCILIATION`. No broker query, repair, reset, or
reconciliation service is implemented.

## 25. Broker-truth exclusion

Successful dry run stops at `READY_FOR_DISPATCH`. It never claims submitted,
acknowledged, working, filled, cancelled, replaced, broker rejected, or external
order ID facts.

## 26. Determinism

Fingerprints:

- `pdr-` request
- `pdo-` result
- `pdt-` receipt
- `pdf-` failure

No hidden clock, random generation, environment access, or mutable global state
is used.

## 27. Purity

The package performs no filesystem read/write, network access, environment
read, subprocess, broker construction, simulator access, persistence, event
publication, metrics, logging, scanner invocation, supervisor invocation, UI,
API, or CLI invocation.

## 28. Security

Contracts normalize safe reason/message codes and reject sensitive terms in
operator-facing dry-run codes.

## 29. Architecture boundaries

Architecture tests enforce approved imports, no runtime side-effect tokens, no
broker/persistence ports, no Live/effect-capable modes, and no runtime wiring.

## 30. Tests added

`tests/test_paper_execution_dry_run.py` adds 169 focused tests.

## 31. Architecture tests

`tests/test_architecture_dependencies.py` now includes dry-run boundary tests.

## 32. Verification results

Focused dry-run and architecture tests passed locally before full verification.

## 33. Known limitations

Dry-run has no durable replay store, no broker reconciliation, no persistence,
and no runtime integration.

## 34. Deferred capabilities

Deferred to later slices: execution persistence and idempotency foundation,
broker adapter certification, controlled Paper submission, reconciliation
services, event publication, metrics, UI/API/CLI, and Live analysis.

## 35. Risks

Dry-run remains only as strong as caller-supplied immutable facts. It does not
prove broker availability, market capability, account status, buying power, or
external readiness.

## 36. Next recommended slice

V41-PQ-001F5E — Execution Persistence and Idempotency Foundation.

## 37. Explicit non-execution statement

The dry-run executor is side-effect free. `WOULD_DISPATCH` does not authorize
execution. No broker port was implemented. No broker adapter was implemented.
No broker was called. No simulator was accessed. No persistence was
implemented. No durable idempotency was implemented. No runtime wiring was
added. No broker truth was claimed. No Live behavior was added. V41-PQ-001
remains incomplete.
