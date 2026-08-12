# V41-PQ-001F3 Implementation Report: Shadow-Mode Paper Qualification Invocation

## 1. Purpose

Introduce a read-only shadow comparison path that can observe an existing Paper
runtime decision, invoke the Paper qualification facade, and compare safe facts
without controlling or mutating the current Paper workflow.

## 2. Scope implemented

- Immutable legacy Paper decision contract.
- Immutable shadow invocation request.
- Immutable shadow comparison result.
- Deterministic shadow invocation identity.
- Agreement and mismatch classifications.
- `PaperQualificationShadowRunner`.
- Pure comparison logic.
- Identity and trace continuity checks.
- Safe mismatch records.
- Unit tests and architecture fitness tests.

## 3. Scope excluded

No runtime wiring, scanner integration, supervisor integration, feature flag,
configuration switch, broker execution, cancellation execution, simulator
mutation, observation polling, reconciliation execution, persistence, filesystem
logging, event publishing, metrics, API, CLI, UI, Live support, or legacy-path
replacement is included.

## 4. Architecture

The implemented path is:

`LegacyPaperDecision` + `PaperRuntimeRequest` → `PaperQualificationShadowRunner`
→ injected `PaperQualificationFacade` → `PaperQualificationFacadeResult` →
shadow comparison → `PaperQualificationShadowResult`.

The shadow result is returned only to tests or future callers.

## 5. Files created

- `volcanoes/application/qualification/integration/shadow.py`
- `tests/test_paper_qualification_shadow_mode.py`
- `docs/engineering/V41_PQ_001F3_IMPLEMENTATION_REPORT.md`

## 6. Files updated

- `volcanoes/application/qualification/integration/__init__.py`
- `volcanoes/application/qualification/integration/errors.py`
- `tests/test_architecture_dependencies.py`
- `docs/engineering/V41_PQ_001_DESIGN.md`
- `docs/roadmap/EDUTRADERAI_V4_1_ROADMAP.md`

## 7. Legacy decision contract

`LegacyPaperDecision` records safe existing Paper decision facts: environment,
legacy decision ID, runtime request ID, qualification run ID, command ID,
correlation ID, idempotency key, expected revision, decision type, action type,
optional safe order intent, approval state, cancellation intent, reconciliation
intent, emergency-stop state, reason code, and safe metadata.

## 8. Shadow request model

`PaperQualificationShadowRequest` pairs one `PaperRuntimeRequest` with one
`LegacyPaperDecision`. If no shadow ID is provided, it derives a deterministic
`qis-` ID from canonical identity and order-intent fields.

## 9. Shadow result model

`PaperQualificationShadowResult` preserves the shadow ID, legacy decision,
optional facade result, status, mismatch classifications, matched fields,
mismatch records, qualification identity, transition/revision fields,
qualification state/result, replay status, and the constants
`action_executed=False` and `legacy_behavior_changed=False`.

## 10. Comparison statuses

- `MATCH`
- `MATCH_WITH_NONCONSEQUENTIAL_DIFFERENCE`
- `MISMATCH`
- `INCOMPARABLE`
- `QUALIFICATION_ERROR`
- `INVALID_SHADOW_INPUT`

## 11. Mismatch classifications

The stable classification set includes environment, identity, proceed/block
disagreement, action kind, order intent, approval, cancellation, reconciliation,
emergency stop, revision, replay, terminal result, unsupported legacy decision,
unsupported qualification action, and insufficient comparison facts.

## 12. Comparison rules

The comparison checks environment, identity continuity, action kind,
consequential allow/block behavior, submission intent, cancellation intent,
reconciliation intent, emergency-stop behavior, order intent, terminal
qualification result when comparable, replay behavior, and revision continuity.

Cancellation requests are not equated with cancellation confirmation. Broker
acknowledgment is not equated with fill. Missing order facts produce
`INCOMPARABLE`, not a false match.

## 13. Shadow runner API

`PaperQualificationShadowRunner(facade).evaluate(request)` accepts an injected
`PaperQualificationFacade` and one `PaperQualificationShadowRequest`.

## 14. Operation ordering

The runner validates Paper-only scope and identity continuity before facade
invocation, invokes the facade exactly once, validates returned identity, then
compares legacy and qualification facts. It performs no retries.

## 15. Identity continuity

The runtime request and legacy decision must agree on environment, runtime
request ID, qualification run ID, command ID, correlation ID, idempotency key,
expected revision, and order intent when both sides provide one. Facade results
must also match the originating request identity and previous revision.

## 16. Paper-only enforcement

Live, unknown, or missing environments are rejected before facade invocation.
Returned runtime actions must also be Paper-only.

## 17. Facade invocation

The shadow runner invokes `PaperQualificationFacade`. The facade may invoke
`PaperQualificationService`, but all returned runtime actions remain
descriptive and non-executed.

## 18. Replay behavior

Replay comparison is represented explicitly. Replay-only differences are
classified as nonconsequential when all other safe facts match.

## 19. Failure behavior

Facade errors produce a safe `QUALIFICATION_ERROR` result with the stable reason
code preserved. Pre-facade identity errors raise typed shadow errors and do not
invoke the facade.

## 20. Error model

Added typed shadow errors:

- `PaperQualificationShadowError`
- `ShadowInputValidationError`
- `ShadowIdentityContinuityError`
- `UnsupportedLegacyDecisionError`
- `ShadowComparisonError`

Errors expose stable reason codes and safe messages only.

## 21. Security

Shadow contracts reject known secret-bearing strings in identifiers and metadata.
Tests verify sentinel secret strings do not appear in results, mismatch details,
errors, or derived identities.

## 22. Privacy

No raw broker payloads, account identifiers, credentials, personal identifiers,
local paths, authorization headers, cookies, or exception traces are included in
shadow contracts or results.

## 23. Architectural fitness functions

Architecture tests prove the shadow module has no runtime/infrastructure
imports, does not construct the facade or service, does not call the state
machine, does not import evidence/repositories/events/metrics, and is not wired
into current runtime entry points.

## 24. Test coverage

`tests/test_paper_qualification_shadow_mode.py` covers construction,
Paper-only rejection, identity continuity, deterministic IDs, semantic matches,
consequential mismatches, order-intent mismatches, incomparable results, replay,
facade failures, immutability, no-effect boundaries, secret absence, and the
default qualification scenario through the shadow runner.

## 25. No-external-effect proof

Tests monkeypatch filesystem, network, subprocess, environment, clock, UUID, and
pseudo-random boundaries to fail if shadow evaluation attempts external effects.
All evaluated runtime actions remain descriptive and unexecuted.

## 26. No-runtime-wiring proof

Architecture tests inspect `app.py`, Paper order adapters, scanner execution,
and engine entry points to prove they do not import or invoke shadow contracts
or the shadow runner in this slice.

## 27. Broker boundary

No broker adapter is imported, instantiated, or invoked. No broker call is
added.

## 28. Simulator boundary

No simulator module is imported. No simulator state is read, written, restored,
discarded, or committed.

## 29. Runtime-wiring boundary

No current Paper runtime, scanner, supervisor, Streamlit page, CLI, API, broker
adapter, or runtime controller invokes shadow mode.

## 30. Persistence boundary

No persistence module, repository implementation, database, or filesystem
logging is added.

## 31. Evidence boundary

The shadow runner does not serialize, record, or persist comparison evidence.

## 32. Feature-flag boundary

No feature flag or configuration switch is implemented in this slice.

## 33. Event and metrics boundary

No event publisher is integrated and no metrics are emitted.

## 34. Live-isolation boundary

Live input is rejected. This slice does not authorize any Live behavior.

## 35. Known limitations

- Shadow mode is not invoked by current runtime.
- No feature flag exists.
- No comparison persistence exists.
- No comparison event or metrics publication exists.
- No broker observation polling exists.
- No reconciliation execution exists.

## 36. Rollback

Rollback is removal of `shadow.py`, shadow tests, architecture-test additions,
and documentation updates. Current Paper runtime behavior is not wired to the
shadow runner and therefore remains unchanged.

## 37. Verification results

Focused verification before final release verification:

- `python3 -m pytest -q tests/test_paper_qualification_shadow_mode.py` — 37 passed.
- `python3 -m pytest -q tests/test_paper_qualification_state_machine.py tests/test_paper_qualification_service.py tests/test_paper_qualification_scenarios.py tests/test_paper_qualification_evidence.py tests/test_paper_qualification_integration_contracts.py tests/test_paper_qualification_facade.py tests/test_paper_qualification_shadow_mode.py tests/test_architecture_dependencies.py` — 448 passed.
- Focused Black on changed Python files — PASS.
- Focused Ruff on changed Python files — PASS.
- Focused MyPy on changed Python files — PASS.
- `make verify` — PASS.
- Architecture dependency tests — 38 passed.
- Full pytest suite — 821 passed.
- Branch coverage run — 821 passed.
- Coverage baseline — 82.7% total line/branch combined coverage.

## 38. Next implementation slice

Recommended next slice: V41-PQ-001F4 — Controlled shadow runtime wiring.

F4 should introduce the shadow runner into one carefully selected Paper-only
runtime observation point. It must remain disabled by default, never execute
returned actions, never influence legacy decisions, include instant rollback,
and preserve scanner, supervisor, broker, and simulator behavior.

V41-PQ-001 remains incomplete after F3.
