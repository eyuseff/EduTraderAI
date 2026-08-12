# V41-PQ-001C Implementation Report: Qualification Scenario Harness

## 1. Purpose

V41-PQ-001C implements a deterministic, presentation-neutral scenario harness for ADR-004 Paper qualification flows.

The harness executes approved scenario specifications through the V41-PQ-001B `PaperQualificationService`, which in turn invokes the V41-PQ-001A pure state machine. It provides an executable reference specification for approved Paper qualification behavior without connecting to brokers, simulator runtime state, persistence, UI, CLI, network services, environment variables, or credential sources.

## 2. Scope implemented

- Immutable scenario specification contracts.
- Immutable scenario-step, expectation, context, step-result, and scenario-result contracts.
- Deterministic approved scenario catalog.
- Scenario lookup by ID and version.
- Scenario validation with safe reason codes.
- Scenario harness that invokes `PaperQualificationService`.
- Deterministic non-durable in-memory repository and evidence-recorder ports.
- Scenario tests for positive, negative, recovery, safety, replay, and conflict flows.
- Architecture fitness checks for the scenario boundary.

## 3. Scope excluded

- Broker submission.
- Broker cancellation.
- Broker lookup.
- Reconciliation algorithms.
- Production evidence adapter.
- Production repository.
- Durable event publishing.
- Runtime scheduling.
- CLI or UI integration.
- Current Paper Order workflow integration.
- Live-trading support.

## 4. Architecture

The implemented dependency direction is:

```text
Scenario Specification
        ↓
Qualification Scenario Harness
        ↓
Paper Qualification Service
        ↓
Pure Qualification State Machine
        ↓
Abstract Ports / Deterministic Fakes
```

The harness depends on application qualification contracts and the public service boundary. The state machine and service do not depend on the scenario harness.

## 5. Files created

- `volcanoes/application/qualification/scenario_models.py`
- `volcanoes/application/qualification/scenario_validation.py`
- `volcanoes/application/qualification/scenario_catalog.py`
- `volcanoes/application/qualification/scenario_harness.py`
- `volcanoes/application/qualification/in_memory.py`
- `tests/test_paper_qualification_scenarios.py`
- `docs/engineering/V41_PQ_001C_IMPLEMENTATION_REPORT.md`

## 6. Files updated

- `volcanoes/application/qualification/__init__.py`
- `tests/test_architecture_dependencies.py`
- `docs/engineering/V41_PQ_001_DESIGN.md`
- `docs/roadmap/EDUTRADERAI_V4_1_ROADMAP.md`

## 7. Scenario specification model

`QualificationScenarioSpec` is immutable and declarative. It includes scenario identity, version, title, description, environment, order intent summary, preconditions, ordered steps, terminal expectation, required evidence expectations, side-effect expectations, prohibited behavior, tags, mandatory status, category, and execution policy.

Scenario specifications are data only. They do not contain callables, dynamic imports, broker adapters, state destinations to mutate, file destinations, network clients, or runtime hooks.

## 8. Scenario-step model

`QualificationScenarioStep` is immutable and explicit. Each step declares:

- step ID and sequence;
- step kind;
- application event type;
- expected source state;
- expected transition ID;
- expected revision;
- actor type;
- command and idempotency identity;
- guard facts;
- optional normalized broker observation;
- replay and expected-rejection flags;
- an immutable `QualificationScenarioExpectation`.

The expected destination state is an assertion against the service result, not an instruction to mutate state.

## 9. Scenario catalog

The approved in-code catalog is exposed through:

- `approved_scenario_catalog()`
- `scenario_by_id(...)`
- `build_scenario_catalog(...)`

Catalog ordering is deterministic by scenario ID and version. Duplicate scenario ID/version pairs fail during catalog construction.

## 10. Mandatory scenarios

The catalog implements:

1. `PQ-SCN-005` — default positive Paper acknowledgment, cancellation, no-position scenario.
2. `PQ-SCN-008` — operator rejection before broker submission.
3. `PQ-SCN-002` — precheck failure.
4. `PQ-SCN-009` — emergency stop blocks consequential submission.
5. `PQ-SCN-010` — uncertain submission requires reconciliation.
6. `PQ-SCN-011` — duplicate consequential command replay.
7. `PQ-SCN-012` — idempotency conflict.
8. `PQ-SCN-013` — duplicate broker acknowledgment observation replay.

## 11. Harness API

The public runner is:

```python
QualificationScenarioHarness.run(
    scenario,
    *,
    execution_context,
)
```

Dependencies are injected explicitly:

- `PaperQualificationService`
- `QualificationRunRepository`

The service itself receives the repository and evidence recorder ports.

## 12. Step execution

For each step the harness:

1. Reads current run state through the abstract repository port.
2. Verifies the expected source state.
3. Constructs `QualificationApplicationCommand`.
4. Invokes `PaperQualificationService.execute()`.
5. Checks transition ID, destination state, result, revision, execution-plan kind, side-effect intents, reconciliation flag, replay behavior, and evidence behavior.
6. Records an immutable step result.
7. Stops safely on unexpected behavior.

The harness does not directly invoke `apply_transition`.

## 13. Expected-rejection behavior

Expected rejection steps are first-class scenario assertions. They verify that:

- the application result is rejected;
- reason code and safe message match;
- state and revision remain unchanged;
- no consequential side-effect intent is returned;
- no transition evidence record is written through the recorder.

Unexpected rejections fail the scenario and stop execution.

## 14. Execution-plan assertions

Scenario expectations assert existing public side-effect intent types:

- `REQUEST_OPERATOR_APPROVAL`
- `RECORD_OPERATOR_APPROVAL`
- `PREPARE_BROKER_SUBMISSION`
- `SEND_BROKER_REQUEST`
- `RECORD_BROKER_REFERENCE`
- `REQUEST_BROKER_CANCELLATION`
- `RECORD_BROKER_LIFECYCLE`
- `START_RECONCILIATION`
- `FINALIZE_QUALIFICATION`
- `BLOCK_CONSEQUENTIAL_ACTION`

These remain descriptive. No broker adapter is invoked.

## 15. Evidence assertions

Accepted material transitions create evidence intents through the abstract recorder. The tests assert transition IDs, source/destination state, revisions, command identity, correlation identity, replay suppression, and safe redaction behavior.

Evidence recording remains abstract and non-durable in this slice.

## 16. Determinism

The harness does not read wall-clock time, random UUIDs, environment variables, network state, filesystem state, or global mutable registries. Given the same scenario specification, injected run ID, injected correlation ID, repository state, recorder behavior, and normalized observations, it produces equivalent logical results.

## 17. Failure and safe-stop behavior

Unexpected behavior stops the scenario without attempting compensating action. The result preserves completed step records, the failed step ID, assertion failures, and a safe summary. It never forces state to match the expected final state.

## 18. Scenario result model

`QualificationScenarioResult` reports:

- scenario ID and version;
- harness status;
- run ID;
- total and completed step counts;
- failed step;
- terminal run snapshot;
- transition trace;
- revision trace;
- execution-plan trace;
- side-effect intent trace;
- evidence references;
- replay observations;
- reconciliation requirement;
- assertion failures;
- safe summary;
- proof that no external action was executed.

Harness status is distinct from `QualificationResult`.

## 19. Default scenario transition trace

The default `PQ-SCN-005` trace is:

```text
PQ-TRN-001
PQ-TRN-002
PQ-TRN-005
PQ-TRN-006
PQ-TRN-009
PQ-TRN-010
PQ-TRN-011
PQ-TRN-015
PQ-TRN-017
PQ-TRN-030
```

## 20. Default scenario revision trace

The default scenario starts from revision `0`. Each accepted state-changing transition increments once:

```text
1, 2, 3, 4, 5, 6, 7, 8, 9, 10
```

The final revision is `10`, matching the ten accepted state-changing transitions.

## 21. Idempotency scenarios

`PQ-SCN-011` proves replay of a consequential command does not increment revision, record new evidence, or reproduce a broker action plan.

`PQ-SCN-012` proves reuse of the same idempotency key with materially different payload produces a deterministic conflict, preserves state, preserves revision, and records no new transition evidence.

## 22. Unresolved and reconciliation scenario

`PQ-SCN-010` advances through submission preparation, records send uncertainty, reaches `UNRESOLVED`, and then enters `RECONCILIATION_REQUIRED` through a read-only reconciliation-start transition. It does not propose a blind retry.

## 23. Security controls

Scenario fixtures are checked for credential-like markers. Results and safe summaries do not expose raw broker payloads, credentials, authorization headers, account numbers, or mutable adapter objects.

## 24. Architectural fitness functions

Architecture tests enforce that:

- qualification modules do not import UI, broker, scanner, legacy trading, infrastructure, network, or subprocess modules;
- scenario modules do not touch runtime state, network, filesystem, environment, random, UUID, or wall-clock APIs;
- scenario specifications do not contain callables;
- the harness uses the application service rather than directly invoking the transition engine;
- the state machine and service do not import the scenario harness.

## 25. Test coverage

`tests/test_paper_qualification_scenarios.py` covers catalog uniqueness, scenario validation, default trace, default revisions, execution plans, evidence assertions, expected rejections, unexpected failures, replay, conflict, duplicate broker observations, no-external-effect proof, determinism, immutability, and result/status separation.

## 26. No-external-effect proof

Tests prove that the harness uses only in-memory ports, never instantiates broker adapters, never mutates simulator state, never reads environment variables, and never accesses runtime files during scenario execution.

## 27. Persistence boundary

`InMemoryQualificationRunRepository` is deterministic and non-durable. It exists only as test-safe harness support and is not production persistence.

## 28. Evidence-durability boundary

`RecordingQualificationEvidenceRecorder` stores evidence intents in memory and returns safe references. It does not claim durability.

## 29. Broker boundary

Normalized broker observations are fixtures. They represent facts already observed outside the harness. They are not broker verification and do not call broker APIs.

## 30. Coordination boundary

The harness is process-local and deterministic. It does not implement cross-process locking, durable idempotency, distributed coordination, or restart recovery.

## 31. Known limitations

- No production evidence adapter.
- No production repository.
- No runtime entry point.
- No CLI or UI presentation.
- No real broker verification.
- No durable replay across process restart.

## 32. Rollback

No runtime integration was added. Rollback consists of not importing or executing the scenario harness. Existing Paper Order behavior is unchanged.

## 33. Verification results

Initial focused verification after implementation:

```text
python3 -m pytest -q \
  tests/test_paper_qualification_state_machine.py \
  tests/test_paper_qualification_service.py \
  tests/test_paper_qualification_scenarios.py \
  tests/test_architecture_dependencies.py

242 passed
```

Final verification:

```text
Focused qualification and architecture tests: 242 passed
Focused Ruff: PASS
Focused MyPy: PASS
make verify: PASS
Full pytest suite: 615 passed
Architecture tests: 26 passed
Coverage: 82.1%
```

## 34. Next implementation slice

Next: V41-PQ-001D — Qualification Evidence Adapter.

V41-PQ-001 remains in progress. Broker execution, runtime integration, production persistence, durable evidence storage, and cross-process coordination remain deferred.
