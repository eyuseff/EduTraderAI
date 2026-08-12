# Sentinel ADR-007 Concurrency and Recovery Audit

## Audit result

PASS.

The concurrency and recovery design is safe enough for ADR acceptance. It still requires implementation contracts, backend spike evidence, and durable adapter work before broker execution.

## Optimistic concurrency rule

Aggregate revision is execution-owned, non-negative, starts at zero, increments exactly once for each accepted local transition, and cannot reset or decrement. A stale expected revision changes nothing and cannot activate a side-effect intent.

Snapshot update and transition-journal append must occur atomically.

## Required durable controls

Future correctness relies on:

- unique constraints;
- exact aggregate revision compare-and-swap;
- database transactions;
- row locks or equivalent durable claims where needed;
- durable idempotency reservations;
- broker-reference uniqueness;
- reconciliation records for ambiguity.

Process-local mutexes, in-memory registries, cooldown maps, or symbol locks may optimize local sequencing but cannot be authoritative duplicate-prevention for broker execution.

## Restart behavior by state

| State | Automatic continuation | Broker query | Reconciliation | Operator visibility | New state-changing commands | Repeat dispatch | Cancel/replace |
|---|---|---|---|---|---|---|---|
| CREATED | Allowed for local commands | No | No | Optional | Allowed by revision | No | No |
| ELIGIBILITY_EVALUATED | Allowed for approval/reject path | No | No | Optional | Allowed by revision | No | No |
| APPROVAL_CONFIRMED | Allowed to reserve idempotency | No | No | Optional | Allowed by revision | No | No |
| IDEMPOTENCY_RESERVED | Allowed to prepare dispatch | No | No unless stuck/ambiguous | Visible if stale | Allowed only by reservation state | No | No |
| READY_FOR_DISPATCH | Allowed to prepare dispatch | No | No | Required before real dispatch | Only one authority | No direct repeat after pending | No |
| DISPATCH_PENDING | Conditional only if broker call proven unsent | Usually yes if ambiguity | Yes if send uncertainty exists | Required | Blocked until resolved | No blind repeat | Usually blocked |
| DISPATCHED | No blind continuation | Yes | Often required | Required | Blocked until broker state clear | No | Request only after evidence |
| BROKER_ACKNOWLEDGED | Observation-driven | Yes for freshness | If conflicting | Optional/required by ops | Allowed by revision if safe | No | Allowed by revision |
| PARTIALLY_FILLED | Observation-driven | Yes | If conflicting or stale | Required | Restricted | No | Cancel/replace may be requested; fill wins on race |
| CANCEL_REQUESTED | Continue to cancel preparation | Possibly | If ambiguity | Required | Restricted | No | Same cancel only by idempotency |
| CANCEL_PENDING | Observation-driven | Yes | If ambiguity | Required | Block conflicting commands | No | No blind repeat |
| REPLACE_REQUESTED | Continue to replace preparation | Possibly | If ambiguity | Required | Restricted | No | Same replace only by idempotency |
| REPLACE_PENDING | Observation-driven | Yes | If ambiguity | Required | Block conflicting commands | No | No blind repeat |
| OUTCOME_UNKNOWN | No | Yes | Required | Required | Blocked except reconcile/fail | No | No |
| RECONCILIATION_REQUIRED | No | Yes/read-only evidence | Required | Required | Blocked except reconcile/fail | No | No |

Terminal states reject mutation except bounded reconciliation/failure behavior documented by lifecycle rules.

## Race handling

- Duplicate worker delivery: one CAS/unique reservation wins; losers replay, observe pending, or fail conflict.
- Approval/rejection race: one expected revision wins; stale loser changes nothing.
- Cancellation/fill race: broker-proven fill wins; cancellation request is not cancellation confirmation.
- Replacement/fill race: broker-proven fill wins; replace confirmation is not inferred.
- Broker observation race: duplicate observation suppressed; conflicting observations require reconciliation.
- Reconciliation/ordinary command race: restricted states block ordinary state-changing commands.

## Unknown-outcome recovery

Local state alone cannot prove broker success. Any possible broker acceptance without durable result creates `OUTCOME_UNKNOWN` or `RECONCILIATION_REQUIRED`; restart recovery must discover it and prohibit automatic resubmission.

## Split-brain and dual-authority risk

Legacy and new execution paths must not both submit the same logical order. Before broker execution is authorized, configuration and architecture tests must enforce one execution authority. Rollback may disable the new path, but cannot reset revisions, idempotency records, broker references, or unknown outcomes.
