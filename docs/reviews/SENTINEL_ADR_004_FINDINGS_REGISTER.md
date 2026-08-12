# Sentinel ADR-004 Findings Register

## Summary by severity

| Severity | Count | Open | Resolved | Deferred |
|---|---:|---:|---:|---:|
| CRITICAL | 0 | 0 | 0 | 0 |
| MAJOR | 4 | 0 | 4 | 0 |
| MINOR | 3 | 1 | 2 | 0 |
| OBSERVATION | 4 | 0 | 0 | 4 |

## Open findings

| ID | Severity | Title | Required | Resolution status |
|---|---|---|---|---|
| SNT-004-007 | MINOR | Operator message next-action language can be refined during UI implementation | Optional | Open, non-blocking |

## Resolved findings

### SNT-004-001 — State ownership required sharper separation

| Field | Value |
|---|---|
| Severity | MAJOR |
| Affected document | `docs/adr/ADR-004-PAPER-QUALIFICATION-STATE-MACHINE.md` |
| Affected section or transition | State model and separation of concerns |
| Problem | The design said state concerns should be separated, but it did not explicitly assign ownership for approval state, broker-reported state, evidence state, reconciliation state, and emergency-stop state. |
| Failure scenario | An implementer could embed broker status or emergency-stop state directly into qualification workflow state and accidentally allow broker events or safety flags to finalize qualification. |
| Consequence | State ownership conflict, false completion, or implementation ambiguity. |
| Recommendation | Add an owner table separating workflow, result, approval, order lifecycle, broker truth, reconciliation, evidence, and emergency-stop concerns. |
| Required or optional | Required |
| Resolution status | Resolved |
| Evidence of resolution | Added `Sentinel correction: state ownership table` to ADR-004. |

### SNT-004-002 — Default mandatory qualification scenario was not explicit enough

| Field | Value |
|---|---|
| Severity | MAJOR |
| Affected document | `docs/adr/ADR-004-PAPER-QUALIFICATION-STATE-MACHINE.md`; `docs/engineering/V41_PQ_001_DESIGN.md` |
| Affected section or transition | Qualification scenarios and semantics |
| Problem | The design listed multiple scenarios and described scenario-dependent pass semantics, but did not choose the mandatory positive v4.1 qualification path. |
| Failure scenario | One implementation might treat broker acknowledgment alone as sufficient while another might require cancellation/no-position proof. |
| Consequence | Invalid qualification result or operator misunderstanding. |
| Recommendation | Declare the default mandatory v4.1 positive scenario as one-share, Paper-only, deliberately non-marketable order, acknowledged, observed as unfilled, cancelled, confirmed cancelled, and reconciled to no open order/no position. |
| Required or optional | Required |
| Resolution status | Resolved |
| Evidence of resolution | Added `Sentinel correction: default mandatory qualification scenario` to ADR-004 and `Sentinel correction: mandatory scenario selection` to the design document. |

### SNT-004-003 — Broad transition sources could be misread as arbitrary mutation

| Field | Value |
|---|---|
| Severity | MAJOR |
| Affected document | `docs/engineering/V41_PQ_001_TRANSITION_TABLE.md` |
| Affected section or transition | PQ-TRN-033, PQ-TRN-034, PQ-TRN-035 |
| Problem | Rows using `Any non-terminal` or `Any persisted active state` were useful templates but could be interpreted as permission to bypass reconciliation, abort uncertain broker effects, or restore state without durable evidence. |
| Failure scenario | A run in `UNRESOLVED` could be finalized or aborted without reconciling possible external broker state. |
| Consequence | False qualification success, unsafe retry, or hidden unresolved order state. |
| Recommendation | Narrow the broad rows with explicit constraints and clarify they are templates, not arbitrary mutation paths. |
| Required or optional | Required |
| Resolution status | Resolved |
| Evidence of resolution | Added `Sentinel correction: narrowed general transitions` to the transition table. |

### SNT-004-004 — Failure destinations were implied but not explicit enough

| Field | Value |
|---|---|
| Severity | MAJOR |
| Affected document | `docs/adr/ADR-004-PAPER-QUALIFICATION-STATE-MACHINE.md`; `docs/engineering/V41_PQ_001_TRANSITION_TABLE.md` |
| Affected section or transition | Transition model and all external-effect transitions |
| Problem | Transition rows had invalid-state behavior but no clear general failure-destination rule for failures before versus after possible external effects. |
| Failure scenario | A broker request could be accepted but local evidence write fails, and implementation might preserve source state rather than moving unresolved. |
| Consequence | Duplicate submission risk and evidence gap. |
| Recommendation | Add a failure-destination rule distinguishing pre-effect failures from possible post-effect failures. |
| Required or optional | Required |
| Resolution status | Resolved |
| Evidence of resolution | Added `Sentinel correction: failure-destination rule` to ADR-004 and `Sentinel correction: explicit failure destinations` to the transition table. |

### SNT-004-005 — Side-effect ordering needed a stronger boundary contract

| Field | Value |
|---|---|
| Severity | MINOR |
| Affected document | `docs/engineering/V41_PQ_001_DESIGN.md` |
| Affected section or transition | Side-effect ordering |
| Problem | The design described separation of transition decision, side-effect execution, evidence persistence, and commitment, but did not name the implementation records that must exist around side effects. |
| Failure scenario | Implementation could mix broker request execution with transition mutation in one untestable function. |
| Consequence | Reduced testability and recovery ambiguity. |
| Recommendation | Add a side-effect boundary contract. |
| Required or optional | Required |
| Resolution status | Resolved |
| Evidence of resolution | Added `Sentinel correction: side-effect boundary contract` to the design document. |

### SNT-004-006 — Transition coverage map needed explicit transition-ID requirements

| Field | Value |
|---|---|
| Severity | MINOR |
| Affected document | `docs/engineering/V41_PQ_001_TEST_STRATEGY.md` |
| Affected section or transition | Transition coverage |
| Problem | The strategy said every transition needs tests, but did not explicitly map high-risk transition IDs to duplicate/replay/reconciliation assertions. |
| Failure scenario | Tests could cover happy-path rows while missing replay safety for broker side effects. |
| Consequence | Insufficient testability. |
| Recommendation | Add an explicit transition coverage map. |
| Required or optional | Required |
| Resolution status | Resolved |
| Evidence of resolution | Added `Sentinel correction: transition coverage map` to the test strategy. |

## Deferred observations

### SNT-004-008 — Persistence durability remains a future decision

| Field | Value |
|---|---|
| Severity | OBSERVATION |
| Affected document | ADR-004 and design |
| Problem | Restart-durable qualification cannot be claimed until V41-PQ-002. |
| Recommendation | Keep persistence deferred but require evidence/state serialization contracts. |
| Resolution status | Deferred to V41-PQ-002 |

### SNT-004-009 — Cross-process coordination remains a future decision

| Field | Value |
|---|---|
| Severity | OBSERVATION |
| Affected document | ADR-004 and design |
| Problem | Process-local locks are insufficient for multi-process deployments. |
| Recommendation | Keep single-process constraint until V41-CP-001. |
| Resolution status | Deferred to V41-CP-001 |

### SNT-004-010 — Exact timeout values remain intentionally unspecified

| Field | Value |
|---|---|
| Severity | OBSERVATION |
| Affected document | ADR-004 |
| Problem | Timeout constants are not selected. |
| Recommendation | Select them during implementation based on broker API behavior and tests. |
| Resolution status | Deferred |

### SNT-004-011 — UI entry point remains a future product choice

| Field | Value |
|---|---|
| Severity | OBSERVATION |
| Affected document | Design |
| Problem | The design forecasts CLI or admin entry points but does not choose one. |
| Recommendation | Choose the entry point only after implementation authorization. |
| Resolution status | Deferred |

## Document changes made

- ADR-004 status changed from Proposed to Accepted after all required corrections were incorporated.
- ADR-004 gained Sentinel acceptance record, state ownership table, default mandatory scenario, and failure-destination rule.
- V41-PQ-001 design gained side-effect boundary contract and mandatory scenario selection.
- Transition table gained narrowed general transition constraints and explicit failure-destination guidance.
- Test strategy gained transition coverage map.
- Roadmap status updated to ADR-004 accepted after Sentinel review; V41-PQ-001 ready for implementation only after separate implementation authorization.

## Residual risk

The remaining risks are implementation risks, not ADR blockers: persistence durability, cross-process coordination, exact timeout constants, event-publisher durability, and UI entry-point selection remain deferred and must not be claimed by V41-PQ-001 alone.

## Implementation blockers

No critical or major ADR blockers remain. Implementation still requires separate authorization and must preserve all deferred boundaries.
