# V41-PQ-001F1 Implementation Report: Paper Integration Contracts

## 1. Purpose

V41-PQ-001F1 implements the pure contract and compatibility-translation layer
needed for later Paper qualification runtime integration.

This slice creates typed models for Paper runtime requests, runtime action
requests, and normalized runtime observations, plus deterministic translators to
and from existing V41-PQ-001 qualification application contracts.

## 2. Scope implemented

- Paper-only environment model.
- Immutable runtime request contract.
- Immutable safe order-intent contract.
- Immutable runtime action-request contract.
- Immutable normalized runtime-observation contract.
- Safe integration metadata normalization.
- Deterministic identity derivation for action requests.
- Runtime request to `QualificationApplicationCommand` translation.
- `QualificationExecutionPlan` to runtime action-request translation.
- Normalized observation to `QualificationApplicationCommand` translation.
- Typed safe integration errors.
- Architecture fitness checks for the integration package.
- Focused unit tests and no-external-effect proof.

## 3. Scope excluded

- Integration facade.
- Application-service invocation.
- State-machine invocation.
- Broker-side-effect executor.
- Broker adapter invocation.
- Simulator adapter invocation.
- Feature flag.
- Shadow mode.
- Runtime wiring.
- Configuration changes.
- Persistence.
- Reconciliation execution.
- Event publishing.
- Operational metrics.
- Live support.
- API, CLI, or UI entry points.

## 4. Architecture

Implemented dependency direction:

```text
Existing Runtime Models
        ↓
Qualification Integration Contracts
        ↓
Pure Compatibility Translators
        ↓
Qualification Application Contracts

QualificationExecutionPlan
        ↓
Pure Action-Request Translator
        ↓
Typed RuntimeActionRequest

NormalizedRuntimeObservation
        ↓
Pure Observation Translator
        ↓
QualificationApplicationCommand
```

The integration package depends only on the standard library and public
qualification contracts/application command types.

## 5. Files created

- `volcanoes/application/qualification/integration/__init__.py`
- `volcanoes/application/qualification/integration/contracts.py`
- `volcanoes/application/qualification/integration/errors.py`
- `volcanoes/application/qualification/integration/translation.py`
- `volcanoes/application/qualification/integration/validation.py`
- `tests/test_paper_qualification_integration_contracts.py`
- `docs/engineering/V41_PQ_001F1_IMPLEMENTATION_REPORT.md`

## 6. Files updated

- `tests/test_architecture_dependencies.py`
- `docs/engineering/V41_PQ_001_DESIGN.md`
- `docs/roadmap/EDUTRADERAI_V4_1_ROADMAP.md`

## 7. Integration contract model

The public integration package is
`volcanoes.application.qualification.integration`.

Public contracts include:

- `PaperIntegrationEnvironment`
- `RuntimeRequestKind`
- `IntegrationOrderType`
- `IntegrationTimeInForce`
- `RuntimeActionKind`
- `RuntimeObservationType`
- `SafeOrderIntent`
- `PaperRuntimeRequest`
- `RuntimeActionRequest`
- `NormalizedRuntimeObservation`

All public models are frozen dataclasses or `StrEnum` values.

## 8. Paper environment model

`PaperIntegrationEnvironment` distinguishes `PAPER` and `LIVE`.

Every public translator and environment-bearing model invokes the Paper-only
guard. `PAPER` is accepted. `LIVE`, unknown values, and missing values fail
deterministically. There is no implicit fallback to Paper or Live, and no
environment-variable read.

## 9. Runtime request contract

`PaperRuntimeRequest` carries safe runtime facts:

- environment;
- runtime request ID;
- qualification run/scenario IDs;
- request kind;
- command ID;
- correlation ID;
- idempotency key;
- expected revision;
- actor type;
- explicit timestamp;
- optional safe order intent;
- supplied guard facts;
- optional safe object reference;
- optional reason code;
- safe metadata.

It contains no credentials, account identifiers, raw broker payloads, SDK
objects, filesystem paths, or arbitrary mutable payloads.

## 10. Runtime action-request contract

`RuntimeActionRequest` is a description of a future runtime action. It is not
proof that an action occurred.

Supported action kinds are:

- `PREPARE_BROKER_SUBMISSION`
- `REQUEST_BROKER_SUBMISSION`
- `REQUEST_BROKER_CANCELLATION`
- `START_RECONCILIATION`
- `BLOCK_CONSEQUENTIAL_ACTION`
- `FINALIZE_WITHOUT_EXTERNAL_EFFECT`
- `NO_RUNTIME_ACTION_REQUIRED`

The contract does not contain broker acknowledgment, completed cancellation,
fill, broker status, or successful-submission fields.

## 11. Normalized observation contract

`NormalizedRuntimeObservation` represents reported broker-neutral facts for
later facade slices. It does not decide transitions.

Supported observation types include broker acknowledgment, broker rejection,
uncertain broker outcome, cancellation confirmation/rejection, partial/complete
fill observation, reconciliation resolution/inconclusive status, order presence
facts, and position facts. Only observations with explicit safe qualification
event mappings translate in this slice.

## 12. Identity propagation

Callers supply:

- qualification run ID;
- scenario ID where applicable;
- command ID;
- correlation ID;
- idempotency key;
- expected revision;
- runtime request ID or observation ID.

`RuntimeActionRequest.action_request_id` is derived deterministically as:

```text
qia-<sha256(canonical-json([
  "action",
  environment,
  qualification_run_id,
  transition_id,
  command_id,
  correlation_id,
  idempotency_key,
  previous_revision,
  action_kind
]))>
```

Equivalent input produces the same identity. Materially different input produces
a different identity. No random value, clock read, Python `repr`, dictionary
iteration order, or secret-bearing value is used.

## 13. Runtime-request translation

`runtime_request_to_qualification_command(...)` translates a
`PaperRuntimeRequest` into the existing `QualificationApplicationCommand`.

The translator:

- enforces Paper environment first;
- preserves command ID, correlation ID, idempotency key, expected revision, actor
  type, run ID, and scenario ID;
- normalizes order facts into a deterministic payload fingerprint;
- passes supplied guards through without inventing missing approval or broker
  facts;
- invokes no service, state machine, evidence recorder, broker, or persistence
  adapter.

## 14. Execution-plan translation

`execution_plan_to_runtime_action_request(...)` translates an accepted
`QualificationExecutionPlan` into a descriptive `RuntimeActionRequest`.

The translator maps descriptive side-effect intents to action descriptions but
does not execute them. A broker-submission action request does not claim broker
acknowledgment. A cancellation action request does not claim cancellation
success. A reconciliation action request does not claim reconciliation
resolution.

## 15. Observation translation

`observation_to_qualification_command(...)` translates supported
`NormalizedRuntimeObservation` values into `QualificationApplicationCommand`.

Acknowledgment does not imply fill. Cancellation request does not imply
cancellation confirmation. Uncertain broker outcomes remain timeout/uncertainty
commands. Order absence alone is unsupported because it does not prove no
position or successful cleanup.

## 16. Validation

Validation rules include:

- no missing environment;
- Paper-only guard;
- non-empty safe identifiers;
- non-negative integer revisions with booleans rejected;
- positive integer quantities with booleans rejected;
- supported order types only;
- limit prices required for limit/bracket-limit intents;
- market orders cannot carry irrelevant limit prices;
- binary floats, NaN, and Infinity rejected;
- timestamps must be timezone-aware and normalize to UTC;
- symbols normalize to uppercase.

## 17. Safe metadata

Metadata must be an immutable tuple of key/value pairs. Supported values are
strings, integers, booleans, `None`, and tuples of those scalar values.

Raw payloads, broker payloads, secret-like keys, secret-like values, local path
strings, mappings, sets, callables, exception objects, SDK objects, and arbitrary
objects are rejected.

## 18. Error model

Typed safe errors include:

- `QualificationIntegrationError`
- `PaperEnvironmentRequiredError`
- `UnsupportedRuntimeRequestError`
- `RuntimeRequestValidationError`
- `UnsupportedExecutionPlanError`
- `UnsupportedRuntimeObservationError`
- `IntegrationIdentityError`
- `IntegrationTranslationError`
- `UnsafeIntegrationMetadataError`

Errors provide stable reason codes and safe messages. They do not include raw
payloads, credentials, exception traces, or broker-success claims.

## 19. Security

The integration layer rejects secret-bearing fields and unsafe metadata. Tests
use fake sentinel values and verify they do not appear in translated commands,
action requests, observations, derived IDs, or exception text.

## 20. Privacy

The integration contracts do not include account numbers, personal information,
credentials, authorization headers, cookies, or raw broker payloads.

## 21. Architectural fitness functions

Architecture tests enforce that the integration package:

- does not import concrete broker adapters;
- does not import simulator implementations;
- does not import runtime controllers;
- does not import event publishers;
- does not import infrastructure, network, database, filesystem, CLI, or UI
  modules;
- does not perform environment reads, random generation, wall-clock reads,
  subprocess calls, or filesystem access;
- does not invoke `PaperQualificationService`;
- does not call the state machine or `apply_transition`;
- is not imported by core qualification state-machine, service, evidence, or
  scenario modules.

## 22. Test coverage

`tests/test_paper_qualification_integration_contracts.py` covers Paper
environment acceptance, Live/unknown/missing environment rejection, immutability,
identity preservation, semantic validation, timestamp normalization, symbol
normalization, runtime-request translation, execution-plan translation,
observation translation, safe metadata, secret exclusion, deterministic action
identity, and no-external-effect proof.

## 23. No-external-effect proof

The focused no-effect test monkeypatches external-effect sentinels such as
filesystem open, socket creation, subprocess execution,
`PaperQualificationService.execute`, `state_machine.transition`, and
`state_machine.apply_transition`. It then exercises all three public translator
paths. Any attempted external effect fails the test.

## 24. Broker boundary

No broker adapter is imported, instantiated, or invoked. No broker request is
submitted, cancelled, queried, or inferred.

## 25. Simulator boundary

No simulator adapter is imported, instantiated, or invoked. No simulator state
file is read or written.

## 26. Persistence boundary

No qualification state is persisted. No repository implementation is added.
Restart durability remains deferred to V41-PQ-002.

## 27. Evidence boundary

The integration layer does not generate evidence, serialize evidence, record
evidence, or publish events. Evidence remains owned by the qualification evidence
adapter and recorder port.

## 28. Feature-flag boundary

No feature flag is implemented. Future runtime slices must add flag behavior
separately and fail closed.

## 29. Runtime-wiring boundary

No runtime entry point is connected. `app.py`, broker adapters, scanner runtime,
and simulator behavior are unchanged.

## 30. Live-isolation boundary

Live values are rejected by the integration contracts and translators. This
slice does not support Live behavior and does not authorize Live trading.

## 31. Known limitations

- No facade exists yet.
- No runtime service invokes these translators yet.
- No broker side-effect executor exists.
- No observation source is connected.
- No targeted cancellation or reconciliation capability is implemented.
- No durable repository or evidence sink exists.
- No feature flag exists.

## 32. Rollback

Rollback is removal of the isolated integration package, focused tests,
architecture-test additions, and documentation status updates. Existing Paper
runtime behavior is not wired to this package and therefore remains unchanged.

## 33. Verification results

Focused verification completed before commit:

- `python3 -m black --check volcanoes/application/qualification/integration tests/test_paper_qualification_integration_contracts.py tests/test_architecture_dependencies.py`
- `python3 -m ruff check volcanoes/application/qualification/integration tests/test_paper_qualification_integration_contracts.py tests/test_architecture_dependencies.py`
- `python3 -m mypy --follow-imports=skip --ignore-missing-imports volcanoes/application/qualification/integration tests/test_paper_qualification_integration_contracts.py tests/test_architecture_dependencies.py`
- `python3 -m pytest -q tests/test_paper_qualification_integration_contracts.py tests/test_architecture_dependencies.py` — 105 passed.
- `python3 -m pytest -q tests/test_paper_qualification_state_machine.py tests/test_paper_qualification_service.py tests/test_paper_qualification_scenarios.py tests/test_paper_qualification_evidence.py tests/test_paper_qualification_integration_contracts.py tests/test_architecture_dependencies.py` — 379 passed.

Full verification:

- `make verify` — PASS.
- Black — PASS.
- Ruff — PASS.
- MyPy deterministic boundary — PASS.
- Architecture dependency tests — 34 passed.
- Full pytest — 752 passed, 0 failed.
- Coverage — 82.2%.

## 34. Next implementation slice

Recommended next slice: V41-PQ-001F2 — Paper Qualification Facade.

F2 should invoke `PaperQualificationService` through the new contracts, remain
non-executing, return translated execution plans, preserve Paper-only
enforcement, and avoid broker, simulator, persistence, and runtime wiring.

V41-PQ-001 remains incomplete after F1.
