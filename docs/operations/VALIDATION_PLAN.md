# EduTraderAI v4.0 Operational Validation Plan

## Purpose and boundary

This plan governs the paper-only observation window between `v4.0.0-rc1` and
v4.0 stable. It validates the existing deterministic platform; it does not
authorize new trading behavior, live capital, new policies, or infrastructure
changes.

The observation log must record both elapsed time and meaningful workflow
counts. Market conditions must never be manufactured merely to reach a trade
quota. Controlled simulator workflows may exercise rejection, drift, duplicate,
and rollback paths regardless of market opportunity.

## Observation window

- Record the UTC start and end of every operator session.
- Observe the RC across at least five separate paper-market sessions spanning at
  least seven calendar days before a stable decision.
- Count manual previews, manual submissions, scanner signals, scanner decisions,
  simulator workflows, Alpaca Paper smokes, rollback exercises, and incidents.
- Scanner submissions from normal market signals have no arbitrary quota. One
  controlled end-to-end scanner submission is required; additional safe,
  naturally occurring submissions strengthen the evidence.
- Reset-aware metrics must be exported at the end of every session because the
  recorder and supervisor state are process-local.

## Stable-release acceptance criteria

| Criterion | Acceptance threshold | Evidence |
|---|---:|---|
| Incorrect submitted quantities | **0** | Compare every broker-submitted quantity to its deterministic submitted plan |
| Material preview/submission drift submitted silently | **0** | All observed drift is rejected before broker submission; record `plan_drift` and broker submissions |
| Unintended duplicate broker submissions | **0** | Broker order evidence, `submissions`, replay/duplicate counters, and idempotency tests |
| Correlation-ID loss | **0** | Controlled event reconstruction tests plus credentialed publisher observation if a publisher is selected |
| Unresolved symbol-lock leaks | **0** | A later same-symbol request succeeds after the active request completes or aborts |
| Supervisor deadlocks | **0** | All supervised requests complete within the operator timeout; no stuck scanner cycle |
| Unexplained application crashes | **0** | Every crash has an incident record and disposition before stable |
| Simulator manual workflow | Pass | At least one approved submit, one policy rejection, one plan-drift rejection, and one rollback submit |
| Simulator scanner workflow | Pass | At least one preview-only cycle, one controlled submission, one replay skip, and one scanner rollback cycle |
| Credentialed Alpaca Paper smoke | Pass | One approved paper-only preview and one safely controlled paper order lifecycle using non-live credentials |
| Rollback behavior | Pass | All three flags exercised: paired manual rollback flags and independent scanner rollback flag |
| Process-local coordination disposition | Documented | Stable release explicitly accepts it with runbook controls or schedules durable coordination before stable |
| `NullEventPublisher` disposition | Documented | Stable release explicitly accepts null publication or selects a tested non-domain adapter before stable |

An instrumentation failure is a release warning and increments
`instrumentation_failures`; it must not alter a trade result. Any unresolved
instrumentation failure blocks the stable decision because observation evidence
would be incomplete.

## Meaningful workflow ledger

For every session, record these counts in `VALIDATION_LOG.md`:

- elapsed wall-clock observation time;
- application starts and clean stops;
- manual approved/rejected previews;
- manual deterministic/rollback submissions;
- scanner cycles, signals, decisions, preview-only outcomes, and submissions;
- broker rejections/exceptions;
- drift, replay, idempotency-conflict, duplicate, symbol-busy, and cooldown outcomes;
- dashboard views and sanitized exports; and
- unexplained crashes or incidents.

### Metric semantics

- `previews` counts deterministic preview-service invocations; every completed
  invocation increments exactly one of `approved_plans` or `rejected_plans`.
- `submissions` counts successful deterministic broker submissions, not button
  clicks or rejected plans. `broker_failures` counts mapped broker rejections and
  exceptions.
- `scanner_signals` counts qualified signals emitted by the scanner;
  `scanner_decisions` counts signals that reach a completed supervisor decision.
- Replay, conflict, duplicate, symbol-busy, and cooldown counters record the
  final supervisor decision once. An idempotent replay does not repeat preview or
  submission counters.
- `event_publication_attempts` counts calls to the configured publisher, including
  the RC's null publisher. It does not imply event durability.
- `instrumentation_failures` means an observation failed open; investigate it as
  an evidence-quality problem.

## Decision process

1. Run `make verify` from the exact tagged source.
2. Complete the runbook smokes in Simulator and, when credentials are available,
   Alpaca Paper.
3. Export and attach the sanitized validation snapshot to the operator-owned RC
   evidence location.
4. Reconcile metric counts with broker order evidence and incident records.
5. Resolve every incident and both infrastructure dispositions.
6. Record a final pass/block decision in the validation log. Stable is blocked if
   any zero-tolerance criterion is nonzero or any required smoke is incomplete.
