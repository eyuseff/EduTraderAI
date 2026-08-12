# Sentinel ADR-007 Transaction Audit

## Audit result

PASS.

The transaction model is safe enough for ADR acceptance and F5E1 contract design. It does not authorize broker execution or a durable backend.

## Core rule

Authoritative local changes for one accepted lifecycle transition must commit together or not at all. No best-effort write may be part of authoritative state. No transaction may span a broker network call.

## Transaction audit matrix

| Transaction | Authoritative reads | Expected revision | Uniqueness checks | Records written | Append-only records | Snapshot changes | Rollback behavior | Crash window | Replay safety | Broker relationship | Failure classification |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Command intake | command, idempotency, aggregate | caller expected revision | command ID, idempotency key/fingerprint, aggregate ID | command, reservation, aggregate if new/current | transition if state accepted | state/revision if transition accepted | all writes rollback | before/during commit = no authority | exact replay after commit | no broker contact | validation/conflict/stale |
| Exact replay | command/reservation | none or current | payload equality | none or replay outcome reference read | none | none | no mutation | safe read-only | deterministic original result | no broker contact | replay |
| Command conflict | command | none | command ID with different fingerprint | optional safe conflict evidence later only | none unless design records conflict fact | none | no mutation | safe | deterministic conflict | no broker contact | command conflict |
| Idempotency replay | reservation | none | key plus same logical fingerprint | none or replay outcome reference read | none | none | no mutation | safe | deterministic original result | no broker contact | idempotency replay |
| Idempotency conflict | reservation | none | key plus different logical fingerprint | optional safe conflict evidence later only | none unless design records conflict fact | none | no mutation | safe | deterministic conflict | no broker contact | idempotency conflict |
| Lifecycle transition | aggregate, command/context | exact aggregate revision | next revision unique | aggregate snapshot, receipt/failure reference if relevant | transition journal entry | next state and revision | all writes rollback | failed commit leaves no accepted transition | duplicate sees replay/stale | no broker call inside | accepted/rejected/stale |
| Dispatch preparation | aggregate, command, approval, idempotency | exact aggregate revision | active dispatch/idempotency/reference constraints | dispatch intent, aggregate | preparation transition | `DISPATCH_PENDING` | all writes rollback | after commit but before call = pending recovery | no automatic duplicate dispatch | before external broker call | pending/unknown if ambiguous |
| Dispatch result | aggregate, dispatch intent, broker result | current dispatch revision | broker reference unique | normalized result, broker reference, receipt/failure, aggregate | result transition | broker-observed or unknown state | all writes rollback | commit ambiguity requires recovery read | duplicate result suppressed | after external broker call | ack/reject/unknown |
| Cancellation request | aggregate, broker reference | exact revision | active cancel command/idempotency | command/reservation/intent, aggregate | cancellation-request transition | `CANCEL_REQUESTED` / `CANCEL_PENDING` | all writes rollback | no blind repeat if uncertain | broker cancel later outside tx | pending/reconciliation |
| Cancellation result | aggregate, broker observation | exact/current observation context | broker observation identity | normalized observation, receipt/failure, aggregate | cancellation result transition | cancelled/filled/unknown/reconcile | all writes rollback | ambiguity reconciles | duplicate observation suppressed | after broker observation | terminal/unknown/conflict |
| Replacement request | aggregate, broker reference | exact revision | active replacement command/idempotency | command/reservation/intent, aggregate | replacement-request transition | `REPLACE_REQUESTED` / `REPLACE_PENDING` | all writes rollback | no cancel-and-submit fallback | broker replace later outside tx | pending/reconciliation |
| Replacement result | aggregate, broker observation | exact/current observation context | broker observation/reference identity | normalized observation, receipt/failure, aggregate | replacement result transition | replaced/filled/unknown/reconcile | all writes rollback | ambiguity reconciles | duplicate observation suppressed | after broker observation | terminal/unknown/conflict |
| Reconciliation | aggregate, broker observations | exact reconciliation starting revision | reconciliation identity | reconciliation record, aggregate, receipt/failure if relevant | reconciliation transition | bounded destination | all writes rollback | unresolved remains visible | repeated reconciliation replays or conflicts | read-only broker evidence only | consistent/conflicting/unresolved |
| Terminal-state update | aggregate, terminal evidence | exact revision | final transition identity | aggregate terminal markers | terminal transition | terminal state | all writes rollback | terminality cannot be inferred from local alone | replay neutral | broker fact if applicable | terminal/failure |

## External-effect crash windows

| Window | Safe restart behavior |
|---|---|
| Before Transaction A | No durable dispatch intent exists; command can be retried normally. |
| During Transaction A | Failed transaction rolls back; no broker call authorized. |
| After Transaction A before broker invocation | Aggregate is discoverable as `DISPATCH_PENDING`; recovery may continue only if broker call is proven unsent or route to operator/reconciliation. |
| Before bytes leave process | Treat like pending if provable; otherwise outcome may be unknown. |
| During broker invocation | Outcome is ambiguous; mark or recover as `OUTCOME_UNKNOWN` / `RECONCILIATION_REQUIRED`. |
| After potential broker acceptance before Transaction B | Blind resubmission prohibited; read-only broker reconciliation required. |
| During Transaction B | Commit ambiguity requires store validation and possible reconciliation. |
| After Transaction B | Replay returns durable result; duplicate broker operation suppressed. |

## Failure atomicity audit

All reviewed failure cases require rollback or fail-closed handling:

- command insert succeeds but reservation fails;
- reservation succeeds but aggregate update fails;
- aggregate snapshot updates but journal append fails;
- journal append succeeds but receipt insert fails;
- broker-reference uniqueness fails;
- approval reference missing;
- reconciliation insert fails;
- commit fails;
- connection lost during commit;
- process crashes after commit response ambiguity;
- migration partially applies;
- backup is incomplete;
- restore contains inconsistent revisions.

No partial authoritative transition may survive a failed transaction.
