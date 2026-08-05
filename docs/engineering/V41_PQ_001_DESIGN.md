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
| Controlled Paper shadow observation | `adapters/paper_order_preview.py::preview_paper_order` | V41-PQ-001F4B adds one disabled-by-default observe-only call site after deterministic preview and before returning the legacy-compatible decision. |
| Runtime observation adapter | `volcanoes/application/qualification/integration/runtime_observation.py` | Builds immutable Paper-only observation contracts and calls an injected `QualificationRuntimeIntegrationBoundary` without executing actions. |

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

## V41-PQ-001B implementation mapping

The second implementation slice maps the application orchestration design to these files:

- `volcanoes/application/qualification/ports.py` contains abstract repository and evidence-recorder ports plus safe result/reference types.
- `volcanoes/application/qualification/service.py` contains typed application commands, descriptive execution plans, application results, application-layer errors, and `PaperQualificationService`.
- `tests/test_paper_qualification_service.py` contains fake-port orchestration tests for the service boundary.
- `tests/test_architecture_dependencies.py` contains qualification-boundary fitness checks.

This mapping does not change the accepted transition semantics. The service invokes the pure transition engine and turns side-effect intents into descriptive plans only. It does not call brokers, mutate simulator state, persist to a production store, publish events, read credentials, expose a runtime entry point, or implement cross-process coordination.

## V41-PQ-001C implementation mapping

The third implementation slice maps the approved scenarios to a deterministic executable reference harness:

- `volcanoes/application/qualification/scenario_models.py` contains immutable scenario, step, expectation, context, step-result, and scenario-result contracts.
- `volcanoes/application/qualification/scenario_validation.py` contains safe scenario specification validation.
- `volcanoes/application/qualification/scenario_catalog.py` contains the approved in-code scenario catalog and stable lookup by scenario ID/version.
- `volcanoes/application/qualification/scenario_harness.py` contains `QualificationScenarioHarness`, which invokes `PaperQualificationService` and asserts expected state-machine behavior without calling brokers or mutating runtime state.
- `volcanoes/application/qualification/in_memory.py` contains deterministic non-durable in-memory ports for harness execution and tests.
- `tests/test_paper_qualification_scenarios.py` contains scenario-harness tests and the default trace/revision assertions.

The mandatory default catalog scenario is `PQ-SCN-005` version `v1`. Its approved trace is `PQ-TRN-001`, `PQ-TRN-002`, `PQ-TRN-005`, `PQ-TRN-006`, `PQ-TRN-009`, `PQ-TRN-010`, `PQ-TRN-011`, `PQ-TRN-015`, `PQ-TRN-017`, and `PQ-TRN-030`.

This mapping does not add a runtime entry point, broker adapter, simulator mutation, production persistence, durable event publication, UI, CLI, live-trading support, or cross-process coordination. V41-PQ-001 remains in progress after this slice.

## V41-PQ-001D implementation mapping

The fourth implementation slice establishes the canonical evidence-adapter contract:

- `volcanoes/application/qualification/evidence.py` contains canonical qualification evidence records, evidence type mapping, schema validation, deterministic JSON serialization, SHA-256 digest helpers, redaction policy, metadata validation, and the port-compatible in-memory canonical recorder.
- `volcanoes/application/qualification/contracts.py` extends `EvidenceIntent` with optional previous/next revision and replay/reconciliation metadata populated by the transition engine.
- `tests/test_paper_qualification_evidence.py` contains canonical evidence-adapter tests and default scenario evidence trace assertions.
- `tests/test_architecture_dependencies.py` contains evidence-adapter boundary checks.

The canonical evidence schema identifier is `qualification-evidence/v1`.

The default `PQ-SCN-005` evidence transition trace is `PQ-TRN-001`, `PQ-TRN-002`, `PQ-TRN-005`, `PQ-TRN-006`, `PQ-TRN-009`, `PQ-TRN-010`, `PQ-TRN-011`, `PQ-TRN-015`, `PQ-TRN-017`, and `PQ-TRN-030`.

Canonical records remain in memory only in this slice. No production persistence, external publisher, broker adapter, simulator mutation, runtime entry point, UI, CLI, live-trading support, or cross-process coordination is added. V41-PQ-001 remains in progress after this slice.

## V41-PQ-001F1 implementation mapping

The first runtime-integration slice establishes pure integration contracts and compatibility translators:

- `volcanoes/application/qualification/integration/contracts.py` contains the Paper environment model, runtime request contract, safe order intent, runtime action-request contract, normalized runtime-observation contract, safe metadata normalization, timestamp normalization, symbol normalization, Paper-only guard, and semantic validation helpers.
- `volcanoes/application/qualification/integration/errors.py` contains typed safe integration errors with stable reason codes and no raw payload exposure.
- `volcanoes/application/qualification/integration/translation.py` contains pure translators from `PaperRuntimeRequest` to `QualificationApplicationCommand`, from `QualificationExecutionPlan` to `RuntimeActionRequest`, and from `NormalizedRuntimeObservation` to `QualificationApplicationCommand`.
- `volcanoes/application/qualification/integration/validation.py` re-exports validation helpers for future integration slices.
- `tests/test_paper_qualification_integration_contracts.py` contains focused contract, translation, Paper-only, identity, metadata, and no-external-effect tests.
- `tests/test_architecture_dependencies.py` contains integration-package boundary checks.

Derived runtime action identities use deterministic SHA-256 over sorted canonical JSON values and the `qia-` prefix. Callers must supply qualification run ID, command ID, correlation ID, idempotency key, expected revision, and timestamps explicitly. The integration layer does not generate identifiers with random values, does not read wall-clock time, and does not read environment variables.

The integration package is intentionally non-executing. It does not invoke `PaperQualificationService`, does not call the state machine, does not execute side-effect intents, does not call brokers, does not instantiate broker adapters, does not touch simulator state, does not persist state, does not record evidence, does not publish events, does not add a feature flag, and does not connect any runtime entry point.

The next slice, V41-PQ-001F2, may add a Paper Qualification Facade that uses these contracts to invoke `PaperQualificationService` while remaining non-executing and Paper-only.

## V41-PQ-001F2 implementation mapping

The second runtime-integration slice adds a narrow non-executing facade over the F1 contracts:

- `volcanoes/application/qualification/integration/facade.py` contains `PaperQualificationFacade` and `PaperQualificationFacadeResult`.
- The facade public API is `PaperQualificationFacade(service).handle(request)`.
- The facade validates the Paper-only request boundary, translates `PaperRuntimeRequest` into `QualificationApplicationCommand`, invokes the injected `PaperQualificationService` exactly once, validates identity continuity, translates the returned `QualificationExecutionPlan` into `RuntimeActionRequest`, validates the descriptive action, and returns an immutable facade result.
- `PaperQualificationFacadeResult` preserves run ID, command ID, correlation ID, idempotency key, transition ID, previous revision, next revision, qualification state, qualification result, replay status, the application result reference, and the translated runtime action. It always reports `action_executed=False`.
- `tests/test_paper_qualification_facade.py` covers facade orchestration, identity continuity, replay behavior, failure behavior, no-external-effect boundaries, and default scenario execution through the facade with in-memory ports.
- `tests/test_architecture_dependencies.py` contains facade-specific fitness checks.

The facade invokes `PaperQualificationService` but remains non-executing. It does not call the state machine directly, does not access repositories directly, does not serialize evidence, does not call brokers, does not instantiate broker adapters, does not touch simulator state, does not publish events, does not emit metrics, does not add a feature flag, and does not connect any runtime entry point.

The next slice, V41-PQ-001F3, may connect the facade into a read-only or shadow runtime path. F3 must not influence current Paper decisions, execute returned runtime actions, submit or cancel broker orders, or change Paper workflow behavior.

## V41-PQ-001F3 implementation mapping

The third runtime-integration slice adds a disabled, unwired shadow comparison
boundary:

- `volcanoes/application/qualification/integration/shadow.py` contains
  `LegacyPaperDecision`, `PaperQualificationShadowRequest`,
  `PaperQualificationShadowResult`, `PaperQualificationShadowRunner`,
  `ShadowComparisonStatus`, `ShadowMismatchClassification`, and
  deterministic shadow identity derivation.
- The shadow public API is
  `PaperQualificationShadowRunner(facade).evaluate(request)`.
- The legacy decision contract records only safe existing Paper decision facts:
  environment, legacy decision ID, runtime request ID, qualification run ID,
  command ID, correlation ID, idempotency key, expected revision, decision type,
  action type, optional safe order intent, approval/cancellation/reconciliation
  intent, emergency-stop status, reason code, and safe metadata.
- The shadow request pairs one `PaperRuntimeRequest` with one
  `LegacyPaperDecision` and derives a stable `qis-` identity when the caller
  does not supply one.
- The shadow result preserves the legacy decision, optional facade result,
  comparison status, ordered mismatch classifications, safe mismatch records,
  identity fields, revision fields, qualification state/result, replay status,
  and the guarantees `action_executed=False` and
  `legacy_behavior_changed=False`.
- The comparison model distinguishes exact matches, nonconsequential replay
  differences, consequential mismatches, incomparable safe-fact gaps, and
  facade/qualification errors.
- Mismatch classifications include environment, identity, proceed/block
  disagreement, action kind, order intent, approval, cancellation,
  reconciliation, emergency stop, revision, replay, terminal result,
  unsupported legacy decision/action, and insufficient comparison facts.
- Identity-continuity rules require the runtime request and legacy decision to
  agree on environment, runtime request ID, qualification run ID, command ID,
  correlation ID, idempotency key, expected revision, and order intent when both
  sides provide one.
- Paper-only enforcement rejects Live, unknown, or missing environments before
  facade invocation.
- The no-effect boundary is explicit: the shadow runner invokes the injected
  `PaperQualificationFacade` exactly once, compares the returned descriptive
  action, and never executes that action.
- The no-runtime-wiring boundary is also explicit: current Paper runtime,
  scanner, supervisor, broker adapters, simulator, UI, CLI, API, metrics,
  events, feature flags, and persistence do not import or invoke shadow mode.

The next slice, V41-PQ-001F4, may introduce one controlled Paper-only runtime
observation point. F4 must remain disabled by default, never execute returned
runtime actions, never influence legacy decisions, and include instant rollback.

## V41-PQ-001F4A implementation mapping

The fourth runtime-integration slice adds the intended sole future
runtime-facing integration seam while keeping it unwired:

- `volcanoes/application/qualification/integration/boundary.py` contains
  `QualificationRuntimeIntegrationBoundary`,
  `QualificationRuntimeBoundaryRequest`, `QualificationRuntimeBoundaryResult`,
  `QualificationRuntimeBoundaryMode`, `QualificationRuntimeBoundaryStatus`,
  deterministic `qib-` boundary identity derivation, and comparison-status
  mapping.
- The boundary public API is
  `QualificationRuntimeIntegrationBoundary(shadow_runner).evaluate_shadow(request)`.
- The request model composes `PaperQualificationShadowRequest`, accepts only
  `QualificationRuntimeBoundaryMode.SHADOW_ONLY`, requires legacy Paper
  behavior to remain authoritative, rejects execution authorization, and carries
  only a safe source identifier and safe metadata.
- The result model preserves boundary ID, mode, status, shadow result,
  qualification run ID, runtime request ID, command ID, correlation ID,
  idempotency key, comparison status, mismatch classifications, revision fields,
  transition ID, described action, and the guarantees `action_executed=False`,
  `legacy_behavior_authoritative=True`, `legacy_behavior_changed=False`, and
  `runtime_connected=False`.
- The dependency direction is future runtime → boundary → shadow runner →
  facade → service. In F4A the future-runtime arrow remains hypothetical:
  current runtime modules do not import or invoke the boundary.
- Identity-continuity rules require matching environment, runtime request ID,
  qualification run ID, command ID, correlation ID, idempotency key, expected
  revision, prior revision, transition identity, and shadow invocation identity.
- The legacy authority rule is encoded explicitly: matches do not authorize
  execution, mismatches do not block legacy behavior, qualification errors do
  not alter runtime behavior, and returned runtime actions are never executed.
- The no-effect boundary excludes brokers, simulator state, runtime entry
  points, scanner, supervisor, UI, CLI, API, feature flags, configuration
  readers, persistence, events, metrics, executor hooks, retries, polling, and
  reconciliation execution.

V41-PQ-001F4B connects exactly one approved Paper runtime observation point to
this boundary. F4B calls only the boundary, remains disabled by default, never
executes returned actions, never alters legacy decisions, and proves zero
behavioral impact.

## V41-PQ-001F4B implementation mapping

The controlled runtime-wiring slice adds the first runtime observation point
while preserving current Paper behavior:

- `adapters/paper_order_preview.py::preview_paper_order` contains the only
  production call site for `observe_paper_preview_decision`.
- The observation call is gated by `PaperQualificationShadowGate.DISABLED` by
  default and `PaperQualificationShadowGate.ENABLED_OBSERVE_ONLY` when
  explicitly injected by a caller.
- `volcanoes/application/qualification/integration/runtime_observation.py`
  contains immutable `PaperPreviewObservationFacts` and
  `PaperQualificationRuntimeObservation` contracts.
- The runtime adapter validates `PaperIntegrationEnvironment.PAPER`, derives
  deterministic IDs, creates `PaperRuntimeRequest`, `LegacyPaperDecision`, and
  `PaperQualificationShadowRequest`, and invokes only
  `QualificationRuntimeIntegrationBoundary.evaluate_shadow`.
- The adapter never constructs the shadow runner, facade, service, state
  machine, evidence adapter, event publisher, broker adapter, simulator, or
  executor.
- The observation result is never authoritative: `action_executed=False`,
  `legacy_behavior_authoritative=True`, and
  `legacy_behavior_changed=False`.
- Scanner, supervisor, broker, simulator, submission, Streamlit UI,
  persistence, events, metrics, configuration, and environment switches remain
  unwired.

## V41-PQ-001F4C implementation mapping

The shadow observation validation slice adds an in-memory harness for completed
boundary results only:

- Validation module location:
  `volcanoes/application/qualification/integration/validation.py`.
- Public API:
  `ShadowObservationValidationHarness.record(result)` and
  `ShadowObservationValidationHarness.summarize()`.
- Input rule: the harness accepts `QualificationRuntimeBoundaryResult` only.
  It does not accept runtime requests, legacy decisions, shadow requests,
  runtime actions, broker responses, simulator state, evidence, or paths.
- In-memory rule: the harness uses a private in-memory accumulator and returns
  immutable `ShadowValidationObservation` and `ShadowValidationSummary`
  values.
- Deterministic summary rule: observations, conflicts, mismatch counts, ratios,
  and summary fingerprints are canonical and insertion-independent where
  appropriate.
- Duplicate model: exact duplicate observations increment deterministic replay
  counts and do not create conflicts.
- Conflict model: the same observation identity with different validation facts
  creates immutable safe conflict records and increments nondeterministic replay
  counters.
- Repeatability model: only repeated equivalent observations can be repeatable;
  one-time observations are not treated as proof of repeatability.
- Identity continuity: the harness counts missing or inconsistent boundary,
  shadow, runtime request, run, command, correlation, and idempotency
  identities.
- Revision continuity: the harness counts previous/expected revision
  mismatches and next-revision regressions.
- Transition continuity: the harness counts boundary/shadow transition identity
  mismatches.
- No-readiness-authorization rule: F4C produces validation facts only and does
  not define readiness thresholds or deployment decisions.
- No-runtime-control rule: validation results never authorize, block, replace,
  or modify legacy Paper behavior.
- No-persistence rule: F4C adds no file output, evidence recorder, database,
  durable store, JSON export, or CSV export.
- No-execution rule: F4C does not execute runtime actions and does not import
  broker, simulator, scanner, supervisor, UI, API, CLI, event, metrics,
  platform configuration, or feature-flag modules.
- Deferred slice: V41-PQ-001F4D should consume immutable F4C summaries and
  define advisory shadow-readiness assessment criteria without authorizing
  runtime execution.

## V41-PQ-001F4D implementation mapping

The shadow readiness-assessment slice adds an advisory-only evaluator for
immutable F4C validation summaries:

- Readiness module location:
  `volcanoes/application/qualification/integration/readiness.py`.
- Public API:
  `ShadowReadinessAssessmentService.assess(summary, policy)`.
- Input rule: readiness accepts `ShadowValidationSummary` and explicit
  `ShadowReadinessPolicy` only.
- Explicit-policy rule: no default policy silently implies operational
  approval. Factory policies are named `strict_validation_policy` and
  `development_observation_policy`.
- Advisory-only rule: every assessment reports `advisory_only=True`,
  `execution_authorized=False`, `runtime_changed=False`,
  `broker_accessed=False`, `simulator_accessed=False`, and
  `live_authorized=False`.
- Decision model: `READY_FOR_NEXT_PHASE`, `NOT_READY`, and
  `INSUFFICIENT_EVIDENCE`.
- Criterion categories: evidence, determinism, continuity, authority,
  execution safety, environment, qualification stability, and comparison
  quality.
- Deterministic precedence: insufficient evidence yields
  `INSUFFICIENT_EVIDENCE` only when no non-evidence criterion fails; otherwise
  hard safety or quality failures yield `NOT_READY`.
- Exact-ratio rule: ratios use `ShadowValidationRatio` and integer
  cross-multiplication without floating-point conversion.
- Mismatch-policy rule: mismatch classifications are preserved by name and
  evaluated against explicit allowed/prohibited policy sets.
- No-runtime-control rule: readiness decisions never authorize, block, replace,
  or modify legacy Paper behavior.
- No-persistence rule: F4D adds no assessment persistence, file output,
  database, event publication, metrics, logging, dashboard, UI, API, or CLI.
- No-execution-authorization rule: `READY_FOR_NEXT_PHASE` means only that the
  evidence satisfies policy for beginning the next engineering design phase.
- Deferred slice: V41-PQ-001F5A should design Paper executor contracts and
  safety boundaries, consume readiness only as advisory evidence, and avoid
  broker execution.

## V41-PQ-001F5A architecture review mapping

The Paper executor architecture-review slice completed the future execution
design without implementing execution:

- Architecture review:
  `docs/engineering/V41_PQ_001F5A_PAPER_EXECUTOR_ARCHITECTURE_REVIEW.md`.
- Lifecycle design:
  `docs/engineering/V41_PQ_001F5A_EXECUTION_LIFECYCLE.md`.
- Contract plan:
  `docs/engineering/V41_PQ_001F5A_EXECUTION_CONTRACT_PLAN.md`.
- Risk register:
  `docs/engineering/V41_PQ_001F5A_EXECUTION_RISK_REGISTER.md`.
- Failure and recovery model:
  `docs/engineering/V41_PQ_001F5A_FAILURE_AND_RECOVERY_MODEL.md`.
- Market-capability model:
  `docs/engineering/V41_PQ_001F5A_MARKET_CAPABILITY_MODEL.md`.
- Implementation plan:
  `docs/engineering/V41_PQ_001F5A_IMPLEMENTATION_PLAN.md`.

F5A accepts execution as a separate bounded context. Qualification may produce
qualified Paper intent and advisory evidence, but qualification must not call
brokers or import executor adapters. Readiness remains advisory only:
`READY_FOR_NEXT_PHASE` is not execution authority.

The future Paper executor architecture requires explicit Paper execution
approval, immutable execution commands, deterministic idempotency, expected
execution revision, stale-request rejection, unknown-outcome handling,
reconciliation, broker isolation, market-capability isolation, Paper-only mode,
and structural Live exclusion.

The future market-capability boundary should absorb broker, account, symbol,
venue, session, lot-size, tick-size, time-in-force, cancellation, and
replacement rules. These rules must not leak into qualification, readiness, the
scanner, or generic execution orchestration.

The F5A review decision is **ACCEPTED WITH CONDITIONS**. The next recommended
slice is V41-PQ-001F5B — Paper Executor Contracts. F5B should define immutable
contracts, enum values, typed failures, and deterministic identity/fingerprint
behavior only. F5B should not call brokers, wire runtime, persist, authorize
execution, or add Live behavior.

## V41-PQ-001F5B implementation mapping

The Paper executor contracts slice implements the inert execution vocabulary
without implementing execution behavior:

- Package root: `volcanoes/application/execution/`.
- Central canonicalization: `volcanoes/application/execution/_canonical.py`.
- Central fingerprinting: `volcanoes/application/execution/fingerprints.py`.
- Public enums: `volcanoes/application/execution/enums.py`.
- Safe construction errors: `volcanoes/application/execution/errors.py`.
- Strong identities:
  `volcanoes/application/execution/identities/`.
- Immutable contracts:
  `volcanoes/application/execution/contracts/`.
- Implementation report:
  `docs/engineering/V41_PQ_001F5B_IMPLEMENTATION_REPORT.md`.

The execution bounded context now exists as immutable contracts only. Commands
remain inert data. Command identity is distinct from command payload
fingerprint. Approval remains evidence only. Readiness remains advisory only.
Paper mode is structurally enforced by a single-member `PaperExecutionMode`.
Execution identities are deterministic, and `PaperExecutionRevision` is
dedicated to execution rather than qualification or broker version semantics.

F5B adds normalized receipts and normalized failures, but it does not add a
broker adapter, broker mapping logic, persistence, idempotency reservation,
stale-revision enforcement, eligibility service, approval evaluation,
market-capability evaluation, runtime wiring, scanner wiring, supervisor
wiring, event publication, metrics, logging, UI, API, CLI, or Live behavior.

## V41-PQ-001F5C implementation mapping

The execution eligibility slice implements a pure advisory eligibility core
over the inert F5B execution contracts:

- ADR: `docs/adr/ADR-005-PAPER-EXECUTION-MODEL.md`.
- Package:
  `volcanoes/application/execution/eligibility/`.
- Public service:
  `PaperExecutionEligibilityService.evaluate(command, policy, evaluated_at=...)`.
- Immutable policy:
  `PaperExecutionEligibilityPolicy`.
- Immutable result:
  `PaperExecutionEligibilityResult`.
- Implementation report:
  `docs/engineering/V41_PQ_001F5C_IMPLEMENTATION_REPORT.md`.

ADR-005 is **Accepted**. The eligibility core consumes immutable execution
commands, evaluates deterministic criteria, and returns immutable advisory
results. Its decisions are `ELIGIBLE`, `INELIGIBLE`, and `INDETERMINATE`.
Decision precedence is deterministic: invalid API input or contradictory policy
raises a typed eligibility error, any failed deterministic criterion yields
`INELIGIBLE`, unresolved mandatory evidence yields `INDETERMINATE`, and all
applicable criteria passing yields `ELIGIBLE`.

Eligibility uses an explicit timezone-aware evaluation timestamp and never reads
the hidden system clock. Approval evidence is evaluated deterministically for
presence, binding, not-yet-valid status, and expiry. The expiry boundary is
exclusive: `expires_at <= evaluated_at` is expired.

The eligibility result remains advisory only. `ELIGIBLE` is not authorization.
`execution_authorized` remains false. `action_executed` remains false.
Readiness remains advisory and independent. Required external prerequisites
that F5C cannot evaluate, including market capability, emergency-stop
clearance, risk clearance, and account clearance, produce `INDETERMINATE`
rather than guessed approval.

F5C does not add broker integration, broker calls, market-capability
evaluation, risk evaluation, account evaluation, emergency-stop lookup,
persistence, durable idempotency reservation, stale-revision storage checks,
runtime wiring, scanner wiring, supervisor wiring, event publication, metrics,
external logging, UI, API, CLI, configuration, dependencies, or Live behavior.

The next recommended slice is V41-PQ-001F5D — Deterministic Dry-Run Executor.

## V41-PQ-001F5D0 lifecycle design mapping

The Paper execution lifecycle design slice completed documentation-only review
before any dry-run executor implementation:

- Accepted ADR:
  `docs/adr/ADR-006-PAPER-EXECUTION-LIFECYCLE.md`.
- State model:
  `docs/engineering/V41_PQ_001F5D0_EXECUTION_STATE_MODEL.md`.
- Transition table:
  `docs/engineering/V41_PQ_001F5D0_TRANSITION_TABLE.md`.
- Event and command model:
  `docs/engineering/V41_PQ_001F5D0_EVENT_AND_COMMAND_MODEL.md`.
- Concurrency and replay model:
  `docs/engineering/V41_PQ_001F5D0_CONCURRENCY_AND_REPLAY_MODEL.md`.
- Reconciliation entry model:
  `docs/engineering/V41_PQ_001F5D0_RECONCILIATION_ENTRY_MODEL.md`.
- Dry-run executor plan:
  `docs/engineering/V41_PQ_001F5D0_DRY_RUN_EXECUTOR_PLAN.md`.
- Review report:
  `docs/engineering/V41_PQ_001F5D0_REVIEW_REPORT.md`.

ADR-006 status is **Accepted** after Project Sentinel review. The F5D0
architecture review decision remains **ACCEPTED WITH CONDITIONS**, with all
critical and major findings closed and F5D1 marked ready for implementation
under strict non-executing scope.

The proposed lifecycle model separates local execution state from broker truth.
Eligibility remains advisory and is recorded only through an explicit future
lifecycle input. `ELIGIBLE` does not mutate state, does not create a submitted
state, and does not authorize dispatch.

The proposed revision rule is: each accepted lifecycle transition increments
the execution aggregate revision exactly once. Rejected transitions, stale
commands, duplicate command replays, duplicate broker observations, and
observational no-ops do not increment revision.

Replay and duplicate rules are explicit: same command ID with same payload
replays the original logical outcome; same command ID with different payload is
a duplicate conflict; same idempotency key with materially different payload is
an idempotency conflict; duplicate broker observations are safe no-ops unless
they contain new monotonic facts.

Unknown outcome is a restricted non-terminal state. It does not imply success
or failure, prohibits automatic resubmission, and requires reconciliation.
Reconciliation entry conditions include outcome ambiguity, local/broker gaps,
duplicate broker references, conflicting fills, cancellation ambiguity,
replacement ambiguity, restart after incomplete dispatch, revision conflicts,
and conflicting observations.

Cancellation and replacement remain distinct lifecycle paths. Cancellation does
not reverse fills; cancellation request is not cancellation. Replacement is
native replace only in the proposed model; replacement request is not
replacement and cancel-and-submit fallback remains rejected.

Dry-run should use a separate future dry-run outcome model rather than entering
broker-truth states. The next recommended implementation slice is
V41-PQ-001F5D1 — Execution Lifecycle Core. F5D0 implemented no executor,
introduced no authority, and added no production Python code.

Sentinel ADR-006 review artifacts:

- Review:
  `docs/reviews/SENTINEL_ADR_006_REVIEW.md`.
- Findings register:
  `docs/reviews/SENTINEL_ADR_006_FINDINGS_REGISTER.md`.
- Transition audit:
  `docs/reviews/SENTINEL_ADR_006_TRANSITION_AUDIT.md`.
- Failure matrix:
  `docs/reviews/SENTINEL_ADR_006_FAILURE_MATRIX.md`.
- Approval checklist:
  `docs/reviews/SENTINEL_ADR_006_APPROVAL_CHECKLIST.md`.

Final Sentinel outcomes: state count 22, transition count 30, command-terminal
states `INELIGIBLE`, `ABORTED_BEFORE_DISPATCH`, `BROKER_REJECTED`, `REPLACED`,
and `FAILED_TERMINAL`; aggregate-terminal states `FILLED`,
`FAILED_TERMINAL`, and `CANCELLED` when no remaining working broker reference
exists; broker-order-terminal observations `FILLED`, `CANCELLED`, and
`BROKER_REJECTED`. `RECONCILIATION_REQUIRED` remains non-terminal and
recoverable. F5D1 authorized scope is pure lifecycle aggregate, state enum,
input/event contracts, transition specification, pure transition function,
optional pure apply-transition function, revision validation,
replay/idempotency decision model, descriptive side-effect intents only, and
descriptive evidence intents only.

## F5D1 implementation status: Paper execution lifecycle core

V41-PQ-001F5D1 implements the accepted ADR-006 Paper execution lifecycle core
as deterministic application contracts under
`volcanoes/application/execution/lifecycle/`.

Implemented lifecycle core:

- exactly 22 accepted Paper execution states;
- exactly 30 transition specifications, `PX-TRN-001` through `PX-TRN-030`;
- immutable lifecycle aggregate, input, context, specification, decision,
  side-effect intent, and evidence-intent contracts;
- expected-revision validation;
- aggregate/correlation identity validation;
- deterministic command replay and conflict classification;
- deterministic idempotency replay and conflict classification;
- deterministic broker-observation replay and conflict classification;
- unknown-outcome and reconciliation-required restrictions;
- bounded reconciliation result handling;
- cancellation and replacement guards;
- partial-fill monotonicity and final-fill guards;
- pure `transition(...)` and pure `apply_transition(...)` APIs.

The implementation preserves the side-effect boundary established by ADR-006.
It emits descriptive intents only and does not add an executor, dry-run
executor, broker port, broker adapter, broker call, persistence, simulator
access, runtime wiring, qualification authority transfer, readiness authority
transfer, event publication, metrics, logging, configuration, dependency, or
Live behavior.

F5D1 focused verification covers lifecycle inventory, transition-table
acceptance, deterministic replay and conflict handling, stale revision
rejection, guard failures, fill monotonicity, cancellation and replacement
safety, reconciliation bounds, immutability, and architecture boundaries.

## F5D2 implementation status: deterministic Paper dry-run executor

V41-PQ-001F5D2 implements a side-effect-free dry-run executor under
`volcanoes/application/execution/dry_run/`.

Implemented dry-run design:

- separate `PaperExecutionEffectMode.DRY_RUN` effect model;
- Paper environment remains distinct as `PaperExecutionMode.PAPER`;
- dry run composes F5C eligibility and F5D1 lifecycle transitions;
- successful dry run stops at `READY_FOR_DISPATCH`;
- successful dry run returns `WOULD_DISPATCH` as simulation only;
- `WOULD_DISPATCH` does not authorize execution;
- result safety booleans always remain false for execution, broker access,
  simulator access, persistence access, runtime mutation, and Live authority;
- deterministic `pdr-`, `pdo-`, `pdt-`, and `pdf-` fingerprints;
- no broker, simulator, persistence, event publisher, metrics, logging, UI,
  API, CLI, dependency, configuration, runtime wiring, or Live behavior.

F5E1A persistence contracts and F5E1B deterministic in-memory reference adapter are now implemented. V41-PQ-001 remains in progress; the next recommended implementation slice is V41-PQ-001F5E-SPIKE — SQLite / PostgreSQL Execution Durability Comparison.

## F5E0 architecture review status: persistence and idempotency

V41-PQ-001F5E0 completes the execution persistence and idempotency architecture review. Sentinel ADR-007 review is completed and ADR-007 is `Accepted`.

Review outcome:

- architecture review decision after Sentinel review: `APPROVED`;
- source-of-truth model: durable execution aggregate plus append-only
  transition journal is local lifecycle truth; broker observations remain
  external broker truth; reconciliation resolves differences without rewriting
  history;
- transaction-boundary model: local authoritative writes commit atomically; no
  transaction spans an external broker call;
- idempotency model: command ID and idempotency key uniqueness must be durable
  before broker execution;
- optimistic-concurrency model: aggregate writes require
  `aggregate_id` plus expected `PaperExecutionRevision` compare-and-swap;
- restart-recovery model: ambiguous and in-flight states require read-only
  recovery or reconciliation, never blind resubmission;
- storage recommendation after Sentinel review: `AUTHORIZE_COMPARATIVE_SPIKE`, with SQLite promising for single-machine Paper execution only if WAL, constraints, migrations, backup/restore, and multi-process contention are proven, and PostgreSQL retained as the multi-worker/multi-host candidate;
- migration and rollback requirements: schema versioning, backups, checksums,
  compatibility checks, and no deletion/rewrite of command history,
  idempotency, revisions, broker references, or unknown outcomes.

Durable persistence remains unimplemented. A non-durable process-local in-memory reference adapter now exists for contract validation only. Broker execution remains prohibited. The next recommended slice is the authorized V41-PQ-001F5E-SPIKE SQLite/PostgreSQL execution durability comparison. No durable backend adapter is authorized until spike evidence is reviewed.

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

## Sentinel ADR-007 review outcome

Project Sentinel completed ADR-007 review on 2026-08-05.

Outcome: APPROVED.

ADR-007 final status: Accepted.

Final source-of-truth decision: immutable execution command record, execution aggregate snapshot, append-only transition journal, normalized broker observations, reconciliation record, supporting evidence, dry-run results, and simulator runtime state in that order. Supporting evidence, dry-runs, and simulator files are never operational execution authority.

Durable record inventory: execution aggregate, execution command, idempotency reservation, lifecycle transition journal entry, broker-reference record, receipt record, failure record, approval record, and reconciliation record.

Transaction-boundary decision: authoritative local writes for one accepted lifecycle transition commit atomically or not at all; no transaction may span a broker network call; future dispatch uses Transaction A for durable intent, an external broker operation outside the transaction, and Transaction B for normalized result or unknown/reconciliation state.

Idempotency decision: command ID binds permanently to one canonical payload fingerprint; idempotency key binds permanently to one logical-operation fingerprint; exact replay returns the original logical result; conflicts fail closed; replay/conflict are revision-neutral and cannot call a broker.

Concurrency decision: aggregate revision is execution-owned, starts at zero, increments exactly once per accepted transition, and is enforced by exact compare-and-swap. Process-local locks may optimize but cannot be authoritative for broker execution.

Restart-recovery decision: consequential non-terminal states are discoverable. Ambiguous external-effect windows become `OUTCOME_UNKNOWN` or `RECONCILIATION_REQUIRED`; blind resubmission is prohibited.

Append-only-history decision: accepted lifecycle transitions are immutable. The materialized aggregate is a current-state view and cannot replace the journal. The design remains materialized aggregate plus append-only journal, not full event sourcing.

Storage decision: `AUTHORIZE_COMPARATIVE_SPIKE` for SQLite/PostgreSQL execution durability comparison. No durable database adapter is authorized until spike evidence is reviewed.

F5E1A status: `IMPLEMENTED` for persistence contracts and unit-of-work ports only.

F5E1B status: `IMPLEMENTED` for a deterministic in-memory reference adapter only.

Broker execution remains prohibited: `NOT_AUTHORIZED`.

## F5E1A implementation status: persistence contracts and unit-of-work ports

V41-PQ-001F5E1A implements the storage-neutral persistence contracts accepted
by ADR-007. The package `volcanoes.application.execution.persistence` now
defines immutable record contracts, repository result contracts, replay and
conflict contracts, restart-discovery query/result contracts, repository
ports, and unit-of-work/session ports.

Implemented boundary:

- persistence bounded-context contracts exist;
- storage-neutral execution aggregate, command, idempotency, transition,
  broker-reference, receipt, failure, approval, and reconciliation records
  exist;
- repository ports exist;
- unit-of-work and command-intake session ports exist;
- explicit expected-revision save contracts exist;
- replay/conflict result contracts exist;
- restart-discovery query contracts exist.

Excluded boundary:

- no concrete adapter;
- no in-memory adapter;
- no durable backend;
- no runtime persistence wiring;
- no durable idempotency;
- no durable lifecycle state;
- no broker port, broker adapter, broker call, or execution authority.

Next recommended slice: `V41-PQ-001F5E-SPIKE — SQLite / PostgreSQL Execution
Durability Comparison`.

The comparative SQLite/PostgreSQL storage spike remains authorized and is
the recommended next slice. V41-PQ-001 remains in progress.

## F5E1B implementation status: deterministic in-memory reference adapter

V41-PQ-001F5E1B implements the process-local in-memory reference adapter for the F5E1A execution persistence contracts and unit-of-work ports. The implementation adds deterministic repository implementations, unit-of-work staging, atomic commit validation, explicit rollback, exact command replay, logical idempotency replay, idempotency conflicts, command conflicts, optimistic revision checks, append-only transition journaling, broker-reference uniqueness, receipt/failure/approval/reconciliation fact storage, and restart-discovery queries over current in-memory state.

The adapter is non-durable. State is lost when the adapter instance is discarded and does not survive process restart. It is not safe across multiple processes, does not implement a database, does not implement filesystem persistence, does not add schemas or migrations, and is not wired into runtime execution. It performs no broker calls and does not authorize Paper or Live trading.

V41-PQ-001 remains in progress. The storage technology spike has selected `SELECT_SQLITE_WITH_MANDATORY_POSTGRESQL_MIGRATION_TRIGGER` for initial local Paper durable adapter design. Next recommended slice: `V41-PQ-001F5E2A — SQLITE DURABLE ADAPTER DESIGN`.


## F5E storage technology spike status: SQLite / PostgreSQL durability comparison

V41-PQ-001F5E-SPIKE is completed as an isolated non-production technology comparison. SQLite runtime evidence was obtained with Python 3.14.6 and SQLite 3.50.4 using synthetic local temporary data only. SQLite executed 30/30 backend-neutral scenarios successfully, including command replay/conflict, idempotency replay/conflict, optimistic compare-and-swap, aggregate plus journal atomicity, rollback, append-only transition identity, broker-reference uniqueness, restart discovery after close/reopen, additive migration, backup/restore, foreign-key rollback, journal/snapshot consistency, and secret exclusion.

PostgreSQL runtime evidence was not obtained because safe local PostgreSQL tooling and Python drivers were unavailable without installing dependencies or changing services. PostgreSQL schema, constraints, compare-and-swap statements, row-locking strategy, migration approach, backup/restore procedure design, and multi-worker implications were assessed statically.

Storage decision: `SELECT_SQLITE_WITH_MANDATORY_POSTGRESQL_MIGRATION_TRIGGER` for the initial local Paper durable adapter design only. SQLite is constrained to single-machine, single application authority, local filesystem, WAL, foreign keys, explicit transactions, busy timeout, migrations, backups, and no network filesystem. PostgreSQL migration is mandatory before multiple hosts, multiple active execution workers, remote shared database access, high write concurrency, public multi-user deployment, managed web deployment, network filesystem use, or availability requirements requiring database failover.

No production adapter, production schema, production migration, runtime wiring, broker port, broker adapter, broker call, simulator integration, scanner/supervisor integration, execution authority, dependency, configuration, UI, API, CLI, credentials, Paper trading enablement, or Live behavior was added. Broker execution remains `NOT_AUTHORIZED` and V41-PQ-001 remains in progress.

Next recommended slice: `V41-PQ-001F5E2A — SQLITE DURABLE ADAPTER DESIGN`.

## F5E2A design status: SQLite durable adapter architecture

V41-PQ-001F5E2A is completed as a design/documentation slice only. It creates
ADR-008 as `Proposed` and defines the future SQLite durable execution adapter
architecture for the F5E1A persistence contracts. ADR-008 is ready for Sentinel
review but is not Accepted.

Design decisions:

- deployment envelope: one machine, local filesystem, one active EMERS
  application deployment authority, one active execution write coordinator,
  and one SQLite execution database;
- database ownership: execution persistence records only; broker truth,
  simulator state, scanner state, portfolio persistence, validation evidence,
  and UI state remain outside SQLite;
- database path: future approved local application data directory outside the
  source tree, Git, `state/`, `state/simulated_broker.json`, build paths,
  temporary spike paths, cloud-synced folders, and network/shared folders;
- connection requirements: `PRAGMA foreign_keys = ON`, `PRAGMA journal_mode =
  WAL`, `PRAGMA synchronous = FULL`, bounded busy timeout, explicit
  transactions, extension loading disabled, and deterministic row handling;
- transaction decision: authoritative writes use `BEGIN IMMEDIATE`; no local
  transaction may span a broker network call;
- CAS decision: aggregate updates require exact `aggregate_id` plus
  `execution_revision` compare-and-swap with exactly one affected row;
- append-only journal decision: transition history is append-only with unique
  `(aggregate_id, next_revision)` and implementation-time triggers recommended
  to reject update/delete on immutable history tables;
- schema decision: future tables map to F5E1A records:
  `execution_aggregates`, `execution_commands`, `execution_idempotency`,
  `execution_transitions`, `execution_broker_references`,
  `execution_receipts`, `execution_failures`, `execution_approvals`,
  `execution_reconciliations`, and `schema_migrations`;
- migration decision: migrations require IDs, checksums, ordering, backup
  prerequisite, startup compatibility checks, validation, and fail-closed
  behavior;
- backup/restore decision: future backups use SQLite backup API or another
  WAL-safe approved method; restore requires maintenance mode, checksum,
  schema, integrity, foreign-key, invariant, and consequential-state
  validation;
- corruption handling: stop authoritative execution, preserve the database,
  do not rewrite history, do not clear idempotency, do not resubmit orders,
  and require operator recovery;
- PostgreSQL migration triggers remain mandatory before multiple hosts,
  multiple active execution workers, shared remote database access, high write
  concurrency, public multi-user deployment, managed web service deployment,
  network filesystem use, failover requirements, or any operating envelope
  beyond validated local SQLite constraints.

No production SQLite adapter, production schema, production migration runner,
database file, runtime persistence wiring, broker port, broker adapter, broker
call, execution authority, dependency, configuration, UI, API, CLI, Paper
trading enablement, or Live behavior was added. Broker execution remains
`NOT_AUTHORIZED` and V41-PQ-001 remains in progress.

Review decision: `ACCEPTED WITH CONDITIONS`.

ADR-008 readiness: ready for Sentinel review.

F5E2B readiness: blocked until Sentinel ADR-008 review authorizes
implementation.

Next recommended slice: `SENTINEL ADR-008 REVIEW`.
