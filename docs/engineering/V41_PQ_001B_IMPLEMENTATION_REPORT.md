# V41-PQ-001B Implementation Report

## 1. Purpose

Record the second implementation slice for the ADR-004 Paper qualification state machine: a presentation-neutral application orchestration service around the pure V41-PQ-001A transition engine.

## 2. Scope implemented

Implemented typed application commands, abstract repository and evidence-recorder ports, descriptive execution plans, application results, application-layer failures, and a service that loads or creates runs, invokes the pure transition engine, records evidence through a port, saves state through a port, and records caller-supplied idempotency decisions.

## 3. Scope excluded

No Alpaca calls, broker calls, order submission, cancellation execution, simulator mutation, Paper Order integration, CLI, UI, API route, persistence infrastructure, database selection, event publishing, retry loop, reconciliation execution, process recovery, cross-process lock, credential read, environment-variable read, market-data access, network I/O, dependency change, or live-trading authorization was added.

## 4. Architecture

The dependency direction is:

```text
Presentation or future runner
    -> PaperQualificationService
    -> pure qualification state machine
    -> abstract repository/evidence ports
```

Future adapters may implement the ports. The service itself does not import concrete adapters or infrastructure.

## 5. Files created

- `volcanoes/application/qualification/ports.py`
- `volcanoes/application/qualification/service.py`
- `tests/test_paper_qualification_service.py`
- `docs/engineering/V41_PQ_001B_IMPLEMENTATION_REPORT.md`

## 6. Files updated

- `volcanoes/application/qualification/__init__.py`
- `volcanoes/application/qualification/state_machine.py`
- `tests/test_paper_qualification_state_machine.py`
- `tests/test_architecture_dependencies.py`
- `docs/engineering/V41_PQ_001_DESIGN.md`
- `docs/roadmap/EDUTRADERAI_V4_1_ROADMAP.md`

## 7. Application service API

`PaperQualificationService.execute(command)` accepts a `QualificationApplicationCommand` and returns a `QualificationApplicationResult`. The result includes the run ID, accepted/rejected outcome, previous run, resulting run, transition decision, descriptive execution plan, evidence references, save result, replay flag, reason code, safe operator message, and reconciliation flag.

## 8. Commands

`QualificationApplicationCommand` carries the qualification run ID, scenario ID, correlation ID, event type, expected revision, command ID, idempotency key, actor type, satisfied guard facts, normalized payload fingerprint, optional object reference, environment identity, and optional recovered state for restart-style transition semantics.

## 9. Ports

`QualificationRunRepository` is an abstract revision-aware repository port with `get`, `save`, `prior_command`, and `record_command`.

`QualificationEvidenceRecorder` is an abstract evidence-recorder port that receives safe `EvidenceIntent` objects and returns `EvidenceRecordReference` values.

No production persistence adapter was implemented.

## 10. Execution plan

`QualificationExecutionPlan` is immutable and descriptive. It carries transition identity, source/destination states, revisions, side-effect intents, evidence intents, retry classification, reconciliation requirement, operator message, correlation ID, command ID, idempotency key, and plan kind.

An execution plan containing `SEND_BROKER_REQUEST` or `REQUEST_BROKER_CANCELLATION` remains a description only.

## 11. Operation ordering

For accepted non-replay transitions, the service orders operations as:

1. Load or create the current run.
2. Read prior idempotency record through the repository port.
3. Invoke the pure transition engine.
4. Build a descriptive execution plan.
5. Record transition evidence through the evidence port.
6. Save the resulting run through the repository port.
7. Record the command decision for future replay.
8. Return the structured result.

For rejected domain transitions, the service returns a structured rejected result and performs no evidence recording or state save.

For replayed commands, the service returns the recorded logical result without evidence recording, state save, or consequential side-effect plan.

## 12. New-run creation

`START_QUALIFICATION` may create an initial immutable `PaperQualificationRun` when the repository has no run for the requested ID. The initial state is `NOT_STARTED`, initial revision is `0`, and initial result is `PENDING`. Duplicate creation of an existing `NOT_STARTED` run is rejected by an application-layer error.

## 13. Revision handling

The pure state machine remains responsible for revision validation. Accepted transitions increment revision once. Rejected domain transitions and replays preserve revision. Repository save remains revision-aware and may report a save conflict separately from transition rejection.

## 14. Idempotency handling

The service obtains prior-command records through the repository port and passes them into the pure transition context. Same key plus equivalent normalized payload replays without duplicate evidence, save, or side-effect plan. Same key plus different payload returns a deterministic domain rejection. Restart-safe idempotency remains dependent on V41-PQ-002 persistence.

## 15. Evidence orchestration

Evidence intent objects are produced by the pure state machine and passed unchanged to the abstract recorder. The service does not redesign the evidence envelope and does not publish events. Evidence-recorder failure is surfaced as `EvidenceRecordingError`, distinct from transition rejection and broker failure.

## 16. Failure behavior

Application-layer failures include missing run, duplicate run creation, save conflict, evidence-recording failure, command validation failure, and generic port failure. Repository and evidence failures are not reported as domain transition decisions. No blind retry occurs.

## 17. Broker boundary

No broker port or concrete broker adapter was added. Broker observations enter only as normalized application commands using accepted event types. The service does not verify broker truth externally and does not submit, cancel, or query orders.

## 18. Reconciliation boundary

The service can return a plan containing `START_RECONCILIATION` and can accept normalized reconciliation-result commands already supported by the transition engine. It does not query brokers, match orders, resolve conflicting broker data, retry reconciliation, or select timeouts.

## 19. Architectural fitness functions

Architecture tests now enforce that the qualification package does not import broker adapters, UI, scanner, concrete infrastructure, network clients, environment readers, simulator state, or runtime side-effect tokens. They also check that the state machine does not import the service layer and that the service depends only on qualification contracts, errors, ports, and state machine.

## 20. Tests

Focused tests cover new-run creation, valid transitions, descriptive side-effect plans, revision increments, stale revisions, unknown runs, duplicate creation, idempotent replay, idempotency conflict, guard failure, invalid transition, terminal-state protection, evidence recording, evidence failure, save conflict, port failure, broker-action plan descriptions, cancellation plan descriptions, reconciliation plan descriptions, emergency-stop guard behavior, Paper-only guard behavior, safe-message redaction, result identity preservation, deterministic operation ordering, deterministic repeated execution, command immutability, and the default scenario orchestration with fake ports.

## 21. Default scenario orchestration

The fake-port default scenario test covers start, prechecks passed, approval requested, operator approved, submission prepared, broker request intent recorded, broker acknowledgment observation, cancellation request intent, broker cancellation confirmation, and qualification finalization to `QUALIFIED` / `PASSED`. No real order is created.

## 22. Security

The service has no credential access, broker imports, network imports, filesystem access, environment-variable reads, wall-clock reads, random ID generation, or concrete infrastructure imports. Tests use fake sentinel secret values only to confirm safe messages and evidence-oriented result rendering do not echo secret-bearing payload fingerprints.

## 23. Atomicity limitations

The service records evidence before saving state for accepted transitions, but no production transaction boundary exists. If evidence recording succeeds and save fails, the service surfaces a save conflict. This is an acknowledged limitation until V41-PQ-002 persistence defines durable atomicity.

## 24. Persistence limitations

The repository is abstract. Test fakes are not production persistence. No database, file store, queue, event store, or manifest integration was added.

## 25. Coordination limitations

No lock, distributed coordination, or cross-process idempotency mechanism was added. V41-CP-001 remains the coordination work item.

## 26. Rollback

Rollback is removal of the service, ports, service tests, architecture-test additions, and documentation status updates. Existing Paper workflows are not integrated with this service and therefore remain unchanged.

## 27. Verification results

Focused tests: `python3 -m pytest -q tests/test_paper_qualification_state_machine.py tests/test_paper_qualification_service.py tests/test_architecture_dependencies.py` passed with 189 tests. Focused Ruff and MyPy checks passed for the changed qualification package and tests. Full verification: `make verify` passed with Black, Ruff, MyPy, 21 architecture tests, import/bytecode checks, Streamlit compilation, 562 pytest tests, 0 failures, and 81.2% coverage.

## 28. Deferred work

Deferred work includes the V41-PQ-001C evidence adapter and qualification scenario harness, future runtime entry point, broker-boundary adapter, durable persistence, reconciliation execution, and cross-process coordination.

## 29. Next slice

Recommended next slice: V41-PQ-001C — evidence adapter and qualification scenario harness, still without modifying existing Paper Order or scanner workflows unless separately authorized.
