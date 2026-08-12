# V41-PQ-001F4B Observation Point Decision

## 1. Decision

V41-PQ-001F4B wires the controlled Paper qualification shadow observation at exactly one runtime point:

`adapters/paper_order_preview.py::preview_paper_order`

The call occurs after deterministic Paper preview has produced the legacy-compatible `RiskDecision` and before the result is returned to the caller.

## 2. Selected observation point

Selected point:

- File: `adapters/paper_order_preview.py`
- Function: `preview_paper_order`
- Runtime path: manual Paper Order deterministic preview
- Boundary called: `QualificationRuntimeIntegrationBoundary.evaluate_shadow`
- Gate: `PaperQualificationShadowGate`
- Default: `DISABLED`
- Enabled mode: `ENABLED_OBSERVE_ONLY`

## 3. Why this point was selected

This point has the smallest safe migration seam:

- The deterministic preview decision already exists.
- The current UI-facing result has already been formed.
- No broker submission has occurred.
- No simulator state mutation is required.
- Paper mode can be asserted as a safe integration fact.
- A shadow boundary can observe the decision without becoming authoritative.
- The return value can remain unchanged for both disabled and enabled modes.

## 4. Runtime authority

The existing deterministic preview result remains authoritative. The qualification observation is non-authoritative and must not change approval, rejection reason, quantity, sizing, order intent, UI behavior, submission behavior, scanner behavior, broker behavior, or simulator state.

## 5. Gate behavior

The gate is explicit and typed:

- `DISABLED`: default; no boundary call is made.
- `ENABLED_OBSERVE_ONLY`: build safe observation contracts and call the injected boundary once when required dependencies are present.

There is no environment-variable switch, persistent configuration switch, executor, or runtime stack construction in this slice.

## 6. Dependency-injection design

The runtime call site accepts an optional `QualificationRuntimeIntegrationBoundary` dependency. It does not construct `PaperQualificationShadowRunner`, `PaperQualificationFacade`, `PaperQualificationService`, state-machine services, evidence persistence, event publishers, or broker executors.

## 7. Paper-only guard

The observation facts use `PaperIntegrationEnvironment.PAPER`. The adapter validates Paper mode before building runtime contracts. Non-Paper inputs are rejected before reaching the boundary.

## 8. Consequential action policy

F4B never executes a returned action. The observation result has fixed safety values:

- `action_executed=False`
- `legacy_behavior_authoritative=True`
- `legacy_behavior_changed=False`

## 9. Failure-containment policy

Typed qualification integration failures are contained as safe observation results. They do not change the preview result.

Generic runtime failures from the legacy preview path are not swallowed. Base exceptions from the injected boundary are not swallowed.

## 10. Rejected alternatives

### `app.py`

Rejected. The Streamlit UI is too presentation-oriented and would couple qualification observation to UI rendering and widget state.

### `adapters/paper_order_submission.py`

Rejected. Submission is consequential and already near broker side effects. Observing there could confuse broker truth with preview truth.

### `adapters/scanner_execution.py`

Rejected. Scanner integration would broaden the slice into automation and supervisor wiring.

### `engine/supervised_brain.py`

Rejected. This would put qualification observation inside scanner orchestration rather than the narrow Paper preview seam.

### `engine/brain.py`

Rejected. This legacy scanner path is intentionally not part of controlled Paper runtime wiring.

### `adapters/paper_broker_execution.py`

Rejected. This adapter is too close to broker execution and order translation.

### `broker/simulated.py`

Rejected. The simulator owns mutable runtime state and must not host qualification observation.

### Broker adapters

Rejected. Concrete broker adapters must remain translation boundaries and must not know about the qualification runtime stack.

## 11. Rollback

Rollback is immediate:

1. Keep the gate at `DISABLED`; or
2. remove the single call site from `adapters/paper_order_preview.py`.

No persisted state, configuration, schema, broker behavior, or scanner behavior depends on F4B.

## 12. Status

Decision: ACCEPTED for V41-PQ-001F4B.

Implementation scope remains controlled Paper preview observation only.
