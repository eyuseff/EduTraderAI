# Sentinel ADR-008 Transaction and CAS Audit

## Audit result

PASS.

The transaction model is precise enough for F5E2B schema/migration foundation and later repository design.

## Core transaction decisions

- Authoritative writes use `BEGIN IMMEDIATE`.
- No local transaction may span a broker call.
- No hidden automatic retry is allowed.
- No `INSERT OR REPLACE` or destructive upsert is allowed.
- Failed authoritative transactions leave no partial rows.
- Lock timeouts surface as normalized infrastructure outcomes.

## CAS decision

Aggregate updates require exact `aggregate_id` plus `execution_revision`; exactly one affected row is required. Zero rows are deterministic stale/not-found outcomes and cannot append a transition or activate side-effect intent.

## Transaction groups

| Group | Review result | Notes |
|---|---|---|
| Command intake | PASS | Command replay/conflict and idempotency replay/conflict are revision-neutral. |
| Lifecycle transition | PASS | Aggregate CAS and journal append must commit atomically. |
| Dispatch preparation | PASS | Durable intent can be designed later; no broker call inside transaction. |
| Dispatch result | PASS | Normalized result/unknown/reconciliation state persisted after broker boundary in later authorized slice. |
| Cancellation request/result | PASS | Broker evidence required for fill/cancel race resolution. |
| Replacement request/result | PASS | Broker evidence required for replace/fill race resolution. |
| Reconciliation | PASS | Append-only reconciliation facts and bounded transitions. |
| Terminal-state update | PASS | Terminality changes only through accepted transition and CAS. |

## Idempotency race decision

New reservation inserts. Compatible duplicate key observes existing binding. Conflicting duplicate key fails conflict. Concurrent identical reservations produce one winner and compatible observers. Concurrent conflicting reservations produce at most one winner and deterministic conflicts. Automatic expiry, release, deletion, and destructive reuse are prohibited.

## Append-only protection decision

Denial triggers are required for commands, transitions, receipts, failures, approvals, reconciliations, and migrations. Idempotency and broker-reference updates are controlled by explicit predicates rather than fully append-only triggers.

## Audit conclusion

No critical or major transaction/CAS findings remain. F5E2B must validate trigger existence and transaction behavior but must not implement repositories or runtime wiring.
