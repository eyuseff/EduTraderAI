# V41-PQ-001F2 Implementation Report: Paper Qualification Facade

## 1. Purpose

V41-PQ-001F2 implements a narrow, Paper-only orchestration facade that connects
the pure V41-PQ-001F1 integration contracts to `PaperQualificationService`.

The facade accepts a typed `PaperRuntimeRequest`, translates it into an existing
qualification application command, invokes the injected service exactly once,
translates any returned execution plan into a descriptive `RuntimeActionRequest`,
and returns an immutable facade result.

## 2. Scope implemented

- `PaperQualificationFacade`.
- Immutable `PaperQualificationFacadeResult`.
- Facade-specific safe typed errors.
- Dependency injection for `PaperQualificationService`.
- Paper-only request enforcement.
- Runtime-request translation through the F1 translator.
- Single service invocation.
- Identity-continuity checks.
- Execution-plan translation through the F1 translator.
- No-executed-action result contract.
- Focused facade tests.
- Architecture fitness checks.
- Implementation report and minimal design/roadmap updates.

## 3. Scope excluded

- Runtime wiring.
- Scanner or supervisor integration.
- Broker execution.
- Cancellation execution.
- Reconciliation execution.
- Observation polling.
- Feature flags.
- Persistence.
- Event publishing.
- Metrics.
- CLI, API, or UI integration.
- Live support.

## 4. Architecture

Implemented flow:

```text
PaperRuntimeRequest
        ↓
PaperQualificationFacade
        ↓
runtime_request_to_qualification_command
        ↓
PaperQualificationService
        ↓
QualificationApplicationResult
        ↓
QualificationExecutionPlan
        ↓
execution_plan_to_runtime_action_request
        ↓
PaperQualificationFacadeResult
```

The facade is an orchestration boundary only. It is not a second state machine,
broker adapter, persistence adapter, retry engine, reconciliation engine,
runtime controller, feature-flag evaluator, evidence serializer, event
publisher, or metrics emitter.

## 5. Files created

- `volcanoes/application/qualification/integration/facade.py`
- `tests/test_paper_qualification_facade.py`
- `docs/engineering/V41_PQ_001F2_IMPLEMENTATION_REPORT.md`

## 6. Files updated

- `volcanoes/application/qualification/integration/__init__.py`
- `volcanoes/application/qualification/integration/contracts.py`
- `volcanoes/application/qualification/integration/errors.py`
- `volcanoes/application/qualification/integration/translation.py`
- `tests/test_architecture_dependencies.py`
- `docs/engineering/V41_PQ_001_DESIGN.md`
- `docs/roadmap/EDUTRADERAI_V4_1_ROADMAP.md`

The F1 contract update adds the existing qualification event names required to
drive approved scenario steps through `PaperRuntimeRequest`. It does not add
runtime effects.

## 7. Facade API

Public API:

```python
PaperQualificationFacade(service).handle(request)
```

The constructor requires an injected `PaperQualificationService` instance. The
facade does not construct the service internally and does not use a global
singleton.

## 8. Facade result model

`PaperQualificationFacadeResult` is immutable and contains:

- qualification run ID;
- service application result reference;
- descriptive runtime action request;
- command ID;
- correlation ID;
- idempotency key;
- transition ID;
- previous revision;
- next revision;
- qualification state;
- qualification result;
- replay flag;
- safe operator message;
- `action_executed=False`.

The result makes clear that the returned runtime action is descriptive only and
has not been executed or broker-confirmed.

## 9. Operation ordering

The facade performs this sequence:

1. Validate Paper-only request boundary.
2. Translate `PaperRuntimeRequest` into `QualificationApplicationCommand`.
3. Invoke `PaperQualificationService.execute` exactly once.
4. Validate identity continuity in the returned application result.
5. Translate `QualificationExecutionPlan` into `RuntimeActionRequest`.
6. Validate returned action identity and Paper environment.
7. Build immutable facade result.
8. Return.

## 10. Environment enforcement

The facade reuses the F1 `require_paper_environment` guard. Live, unknown, or
missing environment values fail before service invocation.

## 11. Request translation

The facade uses `runtime_request_to_qualification_command`. It does not duplicate
translation logic and does not create a parallel command hierarchy.

## 12. Service invocation

The facade invokes `PaperQualificationService` exactly once per accepted request.
It does not call `transition`, `apply_transition`, repository ports, evidence
recorders, or scenario harnesses directly.

## 13. Identity continuity

The facade validates:

- qualification run ID;
- command ID;
- correlation ID;
- idempotency key;
- expected/previous revision;
- runtime action source revision;
- transition ID through the execution plan/action.

Identity mismatch raises `FacadeIdentityContinuityError`. The facade does not
silently repair mismatched identities.

## 14. Execution-plan translation

The facade uses `execution_plan_to_runtime_action_request`. It does not
reinterpret side-effect intents and does not execute returned action requests.

## 15. Replay behavior

Replay semantics remain owned by `PaperQualificationService`. The facade
preserves the replay flag and returns the replay-safe descriptive action. Tests
confirm replay does not reintroduce consequential action and does not increment
revision unexpectedly.

## 16. Failure behavior

- Request translation failure prevents service invocation.
- Service failure prevents action translation and is surfaced as
  `FacadeServiceInvocationError`.
- Identity mismatch prevents action return and causes no second service call.
- Action translation failure causes no retry and is surfaced as
  `FacadeResultValidationError`.
- The facade does not perform retries or manufacture broker observations.

## 17. Error model

New facade errors:

- `PaperQualificationFacadeError`
- `FacadeIdentityContinuityError`
- `FacadeResultValidationError`
- `FacadeServiceInvocationError`

Errors expose stable reason codes and safe messages. They do not include raw
payloads, credentials, broker-success claims, or exception traces.

## 18. Security

The facade introduces no credential, token, password, raw broker payload,
authorization header, account-number, local-path, or personal-information fields.
Tests verify sentinel secrets do not appear in facade result strings, error
text, or derived identities.

## 19. Privacy

The facade returns only safe application/service identities and descriptive
runtime action data. It does not expose broker account metadata or raw external
payloads.

## 20. Architectural fitness functions

Architecture tests enforce:

- the integration package has no runtime or infrastructure imports;
- service dependency is limited to contract translation and the facade;
- the facade does not construct `PaperQualificationService`;
- the facade does not call the state machine;
- the integration package has no broker, simulator, filesystem, network,
  environment, random, wall-clock, event-publisher, or metrics tokens;
- core qualification modules do not import the integration package.

## 21. Test coverage

`tests/test_paper_qualification_facade.py` covers construction with injected
service, Paper/Live behavior, operation order, service call count, identity
preservation, immutable result, descriptive action status, replay behavior,
failure behavior, secret exclusion, no-external-effect proof, and default
scenario execution through the facade.

## 22. No-external-effect proof

The no-effect facade test monkeypatches filesystem open, socket creation,
subprocess execution, `state_machine.transition`, and
`state_machine.apply_transition` to fail. It then exercises facade handling and
confirms returned actions are not executed.

The default scenario facade test uses injected in-memory ports as already
designed. No simulator file is created or accessed.

## 23. Broker boundary

No broker call is added. No broker adapter is imported, instantiated, or invoked.
Runtime actions remain descriptions.

## 24. Simulator boundary

No simulator module is imported. No simulator state is read, written, restored,
or discarded.

## 25. Runtime-wiring boundary

No current Paper workflow, scanner, supervisor, Streamlit page, CLI, API, or
runtime entry point is connected.

## 26. Persistence boundary

The facade does not persist state directly and does not implement a repository.
The injected `PaperQualificationService` remains the application-service owner
for repository/evidence-port orchestration.

## 27. Evidence boundary

The facade does not serialize evidence, record evidence, or access evidence
ports directly.

## 28. Feature-flag boundary

No feature flag is implemented in this slice.

## 29. Metrics boundary

The facade emits no metrics and imports no metrics modules.

## 30. Live-isolation boundary

Live requests are rejected before service invocation. This slice does not
support or authorize Live behavior.

## 31. Known limitations

- No runtime path invokes the facade.
- No feature flag exists.
- No side-effect executor exists.
- No broker observation polling exists.
- No reconciliation execution exists.
- No durable persistence is added.

## 32. Rollback

Rollback is removal of `facade.py`, facade tests, architecture-test additions,
and documentation status updates. Existing Paper runtime behavior is not wired
to the facade and therefore remains unchanged.

## 33. Verification results

Focused verification before commit:

- `python3 -m pytest -q tests/test_paper_qualification_facade.py tests/test_paper_qualification_integration_contracts.py tests/test_architecture_dependencies.py` — 134 passed.
- `python3 -m black --check volcanoes/application/qualification/integration tests/test_paper_qualification_facade.py tests/test_paper_qualification_integration_contracts.py tests/test_architecture_dependencies.py` — PASS.
- `python3 -m ruff check volcanoes/application/qualification/integration tests/test_paper_qualification_facade.py tests/test_paper_qualification_integration_contracts.py tests/test_architecture_dependencies.py` — PASS.
- `python3 -m mypy --follow-imports=skip --ignore-missing-imports volcanoes/application/qualification/integration tests/test_paper_qualification_facade.py tests/test_paper_qualification_integration_contracts.py tests/test_architecture_dependencies.py` — PASS.
- `python3 -m pytest -q tests/test_paper_qualification_state_machine.py tests/test_paper_qualification_service.py tests/test_paper_qualification_scenarios.py tests/test_paper_qualification_evidence.py tests/test_paper_qualification_integration_contracts.py tests/test_paper_qualification_facade.py tests/test_architecture_dependencies.py` — 408 passed.

Full release verification before commit:

- `make verify` — PASS.
- Black formatting check — PASS.
- Ruff static analysis — PASS.
- MyPy deterministic boundary — PASS.
- Architecture dependency tests — 35 passed.
- Import and bytecode smoke tests — PASS.
- Streamlit entry-point compilation — PASS.
- Full pytest suite — 781 passed.
- Branch coverage run — 781 passed.
- Coverage baseline — 82.4% total line/branch combined coverage.

## 34. Next implementation slice

Recommended next slice: V41-PQ-001F3 — Shadow-mode Paper qualification
invocation.

F3 should integrate the facade into a read-only or shadow runtime path, not
influence current Paper decisions, not execute returned runtime actions, not
submit or cancel broker orders, compare legacy and qualification outcomes
safely, preserve Paper-only isolation, and remain disabled by default unless an
accepted design explicitly changes that.

V41-PQ-001 remains incomplete after F2.
