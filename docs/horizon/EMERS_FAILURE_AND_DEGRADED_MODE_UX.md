# EMERS Failure and Degraded-Mode UX

## 1. Purpose

Define safe, visible failure behavior.

## 2. Safe-failure principle

When material state is missing or uncertain, block consequential action and explain recovery.

## 3. Failure taxonomy

Data, broker, authentication, authorization, network, service, event delivery, storage, model, stale state, and unknown order state.

## 4. Data failure

State what data is missing, stale, incomplete, or conflicting.

## 5. Broker failure

State whether broker connection, request, acknowledgment, order state, or reconciliation failed.

## 6. Authentication failure

Block protected action and guide credential/session recovery.

## 7. Authorization failure

Explain missing permission without leaking sensitive data.

## 8. Network failure

Show whether broker state may be affected and whether retry is safe.

## 9. Service failure

Show affected function and block unsafe actions.

## 10. Event-delivery failure

Distinguish local action from external event delivery.

## 11. Storage failure

Block actions that require evidence if evidence cannot be retained.

## 12. Model failure

Block AI interpretation or mark unavailable; do not invent missing output.

## 13. Partial system availability

Clearly show which functions remain safe.

## 14. Stale state

Mark stale timestamps and prevent stale-data approval when required.

## 15. Unknown order state

Require reconciliation before additional material broker action.

## 16. User recovery

Provide safest next action, refresh, cancel where safe, reconcile, or escalate.

## 17. Operator escalation

Escalation should include redacted diagnostics and no secrets.

## 18. Evidence and diagnostics

Record what is known, what is unknown, affected function, money/broker-state impact, blocked actions, safe next action, reconciliation requirement, and evidence availability.

## 19. Prohibited failure behavior

No silent failure, generic success after uncertain submission, retry loops that may duplicate orders, hiding stale data, consequential action when required state is unavailable, or secrets in diagnostics.

## 20. Validation scenarios

Validate broker outage, network timeout after submit, stale data, failed cancellation, event failure, storage failure, and credential revocation.
