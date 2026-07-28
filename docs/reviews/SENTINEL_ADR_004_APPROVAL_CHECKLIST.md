# Sentinel ADR-004 Approval Checklist

## Review result

Overall checklist result: PASS WITH NOTE.

The checklist passes for ADR acceptance after required documentation corrections. The note is that implementation is not authorized by this review alone; V41-PQ-001 requires separate implementation authorization and must not claim persistence or cross-process guarantees.

## State model

| Item | Result | Note |
|---|---|---|
| State ownership is explicit. | PASS | Added owner table in ADR-004. |
| Qualification state is distinct from qualification result. | PASS | ADR separates workflow state and result model. |
| Broker state is not treated as qualification state without scenario rules. | PASS | Mandatory scenario and broker-truth sections clarify this. |
| Every state is reachable or intentionally reserved. | PASS WITH NOTE | Reachability exists conceptually; implementation tests must prove it. |
| Every active state has a recovery or terminal path. | PASS | Transition and failure matrix cover recovery/terminal paths. |
| Terminal states are truly terminal. | PASS | Terminal workflow states are `QUALIFIED`, `DISQUALIFIED`, `ABORTED`. |
| No duplicate state meanings remain. | PASS WITH NOTE | `UNRESOLVED` and `RECONCILIATION_REQUIRED` remain distinct: unknown fact vs active reconciliation requirement. |

## Transitions

| Item | Result | Note |
|---|---|---|
| Every transition has one defined source and destination. | PASS WITH NOTE | Broad-source template rows were narrowed by Sentinel correction. |
| Every transition has guards. | PASS | Guards are documented in each row and guard model. |
| Every transition has evidence requirements. | PASS | Evidence event column and envelope apply. |
| Invalid transitions preserve current state. | PASS | Invalid-transition behavior is explicit. |
| Rejected transitions create no consequential side effect. | PASS | Failure-destination rule confirms this. |
| Approval cannot be bypassed. | PASS | Submission requires approval path. |
| Cancellation requires broker confirmation. | PASS | Cancellation requested and cancelled are separate. |
| Unresolved state requires reconciliation. | PASS | Unresolved cannot become qualified without reconciliation. |
| No direct arbitrary state assignment is required. | PASS | Authoritative transition function required. |

## Idempotency

| Item | Result | Note |
|---|---|---|
| Every consequential command has an idempotency rule. | PASS | Covered in ADR and transition table. |
| Same key and same payload does not repeat external effects. | PASS | Explicit rule. |
| Same key and different payload fails. | PASS | Explicit conflict rule. |
| Duplicate broker events are safe. | PASS | Duplicate-event behavior documented. |
| Out-of-order events are deterministic. | PASS | Reject or reconcile. |
| Restart replay is defined. | PASS WITH NOTE | Full durability deferred to V41-PQ-002. |

## Broker truth

| Item | Result | Note |
|---|---|---|
| Submitted is distinct from acknowledged. | PASS | Explicit. |
| Acknowledged is distinct from filled. | PASS | Explicit. |
| Cancellation requested is distinct from cancelled. | PASS | Explicit. |
| Unknown broker outcome is never treated as success. | PASS | Explicit. |
| Transport success is not broker success. | PASS | Explicit. |
| Reconciliation is required after uncertain external effect. | PASS | Explicit. |

## Evidence

| Item | Result | Note |
|---|---|---|
| Every material transition emits evidence. | PASS | Evidence event and envelope defined. |
| Qualification success requires complete evidence. | PASS | Added mandatory scenario and failure-destination correction. |
| Invalid transitions are diagnosable. | PASS | Diagnostic evidence required where possible. |
| Secrets are excluded. | PASS | Security/redaction requirements are explicit. |
| Broker payloads are minimized and redacted. | PASS | Explicit. |
| Evidence identities and schema versions are defined. | PASS | Envelope includes IDs and schema version. |

## Recovery

| Item | Result | Note |
|---|---|---|
| Crash-before-effect is distinguishable from crash-after-effect. | PASS WITH NOTE | Design requires this; durable proof deferred to V41-PQ-002. |
| Unsafe external retry is prohibited. | PASS | Explicit. |
| Active runs can be reconstructed in future persistence. | PASS WITH NOTE | Requirement defined; not implemented. |
| Unresolved runs block duplicate consequential action. | PASS | Explicit. |
| Reconciliation outcomes are explicit. | PASS | Transition rows 025-028 plus failure matrix. |

## Security

| Item | Result | Note |
|---|---|---|
| Paper environment is enforced. | PASS | Guard and security sections. |
| Environment cannot change during a run. | PASS | Consequential command validation includes environment identity. |
| Approval cannot be reused across materially different payloads. | PASS | Idempotency conflict rule. |
| Emergency stop is enforced at command execution. | PASS | Guard input, not lifecycle state. |
| Errors and evidence do not expose secrets. | PASS | Explicit. |
| No live-trading authorization exists. | PASS | Explicit non-authorization. |

## Testing

| Item | Result | Note |
|---|---|---|
| Every transition maps to tests. | PASS | Transition coverage map added. |
| All invariants are testable. | PASS | Invariants listed. |
| Failure injection is defined. | PASS | Failure tests and matrix. |
| Restart tests are planned. | PASS | Deferred durable implementation noted. |
| Evidence assertions are planned. | PASS | Evidence tests listed. |
| No-side-effect assertions are planned. | PASS | Required in transition coverage map. |
| Determinism is testable. | PASS | Determinism requirements listed. |

## Scope

| Item | Result | Note |
|---|---|---|
| V41-PQ-001 remains state-machine implementation only. | PASS | No implementation occurred. |
| Persistence remains V41-PQ-002. | PASS | Deferred. |
| Cross-process coordination remains V41-CP-001. | PASS | Deferred. |
| No infrastructure was selected. | PASS | Explicit. |
| No live trading was authorized. | PASS | Explicit. |
| No production implementation occurred during Sentinel. | PASS | Documentation-only commit. |
