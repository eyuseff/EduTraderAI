# V41-PQ-001A Implementation Report

## 1. Purpose

Record the first implementation slice for the ADR-004 Paper qualification state machine.

## 2. Scope implemented

Implemented the pure core domain model and deterministic transition engine for the accepted 35-transition Paper qualification state machine.

## 3. Scope not implemented

No broker calls, Alpaca calls, order submission, persistence, event publishing, runtime composition, UI, CLI, configuration change, dependency change, cross-process coordination, timers, retry loops, or external services were implemented.

## 4. Files added

- `volcanoes/application/qualification/__init__.py`
- `volcanoes/application/qualification/contracts.py`
- `volcanoes/application/qualification/errors.py`
- `volcanoes/application/qualification/state_machine.py`
- `tests/test_paper_qualification_state_machine.py`
- `docs/engineering/V41_PQ_001A_IMPLEMENTATION_REPORT.md`

## 5. Files changed

- `docs/engineering/V41_PQ_001_DESIGN.md`
- `docs/roadmap/EDUTRADERAI_V4_1_ROADMAP.md`

## 6. Domain types

Public core types include `PaperQualificationRun`, `QualificationState`, `QualificationResult`, `QualificationEvent`, `TransitionContext`, `TransitionDecision`, `GuardFailure`, `SideEffectIntent`, `EvidenceIntent`, `PriorCommandRecord`, and `TransitionSpec`.

## 7. State model

The implementation includes the exact 20 accepted ADR-004 states and deterministic state classification. Terminal workflow states are `QUALIFIED`, `DISQUALIFIED`, and `ABORTED`.

## 8. Result model

The result enum includes `PENDING`, `PASSED`, `FAILED`, `ABORTED`, and `INCONCLUSIVE`. Workflow state and qualification result remain independent fields.

## 9. Event model

The event model includes accepted command, broker-observation, reconciliation, timeout, restart, abort, and qualification-finalization event types.

## 10. Transition API

The core API is `transition(current_run, event, context) -> TransitionDecision`, with `apply_transition(current_run, decision)` for immutable state application.

## 11. Revision behavior

The caller supplies an expected revision. Accepted transitions increment the revision exactly once. Stale revision raises `StaleRevisionError` before side-effect intent creation. Replayed idempotent decisions do not increment revision.

## 12. Guard behavior

Guards are deterministic input facts supplied through `TransitionContext`. The engine does not read credentials, environment variables, files, market data, clocks, random values, or broker state. Missing guards raise `GuardConditionError` with safe messages.

## 13. Invalid-transition behavior

Unapproved source/event pairs raise typed errors and produce no consequential side-effect intent. `diagnostic_rejection` is available for callers that need a rejected decision with diagnostic evidence intent.

## 14. Idempotency boundary

Idempotency is caller-supplied through `PriorCommandRecord`. Same key and equivalent payload returns a replayed decision with no side-effect intents. Same key and materially different payload raises `IdempotencyConflictError`. No global cache or durable store exists.

## 15. Side-effect intent model

The engine emits side-effect descriptions such as request operator approval, prepare broker submission, send broker request, request broker cancellation, start reconciliation, finalize qualification, block consequential action, or resume/require reconciliation. It never executes those effects.

## 16. Evidence intent model

Every accepted transition emits an `EvidenceIntent` containing transition ID, event type, source and destination state, run/scenario/correlation/command/idempotency identifiers, result, reason code, actor type, environment, safe message, schema version, and optional object reference.

## 17. Broker-truth protections

The transition registry rejects approval-to-acknowledgment, submitted-to-fill, unresolved-to-qualified, cancellation-requested-to-qualified, and other broker-truth shortcuts. Submitted is not acknowledged, acknowledged is not filled, cancellation requested is not cancelled, and unresolved is neither success nor failure.

## 18. Test coverage

Focused tests cover state classification, immutability, all 35 positive transitions, invalid terminal mutation, guard failures, stale revision, invalid broker-truth shortcuts, Paper-only guard enforcement, emergency-stop guard behavior, immutable application, idempotent replay, idempotency conflict, duplicate fill replay, diagnostic rejection, determinism, secret redaction, and the default cancellation-cleanup scenario path.

## 19. Known limitations

This slice is not a complete V41-PQ-001 feature. It does not run qualification, access a broker, persist state, publish events, recover after restart, or integrate with UI/CLI.

## 20. Deferred V41-PQ-001 work

Future slices must add the qualification runner, broker-boundary adapters, evidence sink integration, scenario orchestration, and operator entry point after separate authorization.

## 21. Persistence boundary

No persistence was added. Restart durability remains V41-PQ-002.

## 22. Coordination boundary

No locks or distributed coordination were added. Cross-process safety remains V41-CP-001.

## 23. Security notes

The new package has no broker imports, network imports, credential access, file reads, environment-variable reads, random ID generation, or current-time reads. Tests use fake sentinel secret strings only to verify safe messages and evidence do not echo payload fingerprints.

## 24. Verification results

Focused test run: `python3 -m pytest -q tests/test_paper_qualification_state_machine.py` — 145 passed. Full verification: `make verify` passed with Black, Ruff, MyPy, architecture tests, import/bytecode checks, Streamlit compilation, 535 pytest tests, 0 failures, and 80.8% coverage.

## 25. Rollback

Rollback is removal of the isolated qualification package, focused tests, and documentation status updates. Existing Paper workflows are not integrated with this package and therefore are unchanged.

## 26. Next implementation slice

Recommended next slice: add a presentation-neutral qualification runner using fake broker/evidence ports only, still without modifying existing Paper Order or scanner workflows.
