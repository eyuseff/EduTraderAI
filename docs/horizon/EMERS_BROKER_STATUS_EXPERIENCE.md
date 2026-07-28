# EMERS Broker Status Experience

## 1. Purpose

Define how broker truth is displayed.

## 2. Broker-truth principle

Never display completed when broker state is unresolved. Always distinguish application intent, outbound request, broker acknowledgment, broker execution, and reconciled final state.

## 3. Connection status

Connected, degraded, offline, unauthorized, wrong environment, or unknown.

## 4. Credential status

Loaded, missing, invalid, expired, revoked, or unsafe.

## 5. Environment status

Simulation, Paper, or future live must be visually unmistakable.

## 6. Submission status

Draft, awaiting approval, approved, submission pending, submitted, acknowledged, unresolved, failed.

## 7. Order lifecycle states

Draft, awaiting approval, approved, submission pending, submitted, acknowledged, partially filled, filled, cancellation requested, cancelled, rejected, expired, unresolved, reconciliation required.

## 8. Fill states

No fill, partial fill, full fill, unknown fill, stale fill data.

## 9. Cancellation states

Cancellation available, requested, acknowledged, cancelled, rejected, unresolved.

## 10. Rejection states

Rejected by policy, rejected by broker, rejected by configuration, rejected by stale data, rejected by operator.

## 11. Unknown and unresolved states

Unknown state requires visible warning and reconciliation before further action.

## 12. Reconciliation

Reconciliation compares application records with broker orders, fills, cancellations, and positions.

## 13. Status history

Show timestamped history for material transitions.

## 14. User actions

Allowed actions may include refresh, cancel, reconcile, export evidence, or escalate.

## 15. Evidence

Status changes should link to evidence when material.

## 16. Alerts

Unresolved or rejected broker states may generate alerts.

## 17. Recovery

Recovery should prioritize broker truth and prevent duplicate orders.

## 18. Prohibited assumptions

Do not assume success from request sent, do not hide unknown state, and do not infer fill without broker confirmation.

## 19. Validation requirements

Test each visible state, transition, stale condition, and reconciliation path.

## 20. Open decisions

Open decisions include broker-status wording, polling cadence, websocket use, and mobile status depth.
