# V41-PQ-001F5E0 Optimistic Concurrency Model

## Purpose

Define how future persistence must enforce `PaperExecutionRevision` across
processes. This is design only.

## Required invariant

Every aggregate update must compare the expected execution revision:

```sql
UPDATE execution_aggregates
SET state = ?, revision = ?, updated_at = ?
WHERE aggregate_id = ?
AND revision = ?
```

If zero rows are affected:

- classify stale revision;
- append no transition;
- activate no side-effect intent;
- perform no broker call.

## Initial aggregate creation

Creation uses aggregate ID uniqueness. If an aggregate already exists, command
processing must load and compare revision instead of overwriting it.

## Transition increment

Each accepted lifecycle transition increments revision exactly once through the
same transaction that appends the journal record and updates the materialized
aggregate.

## Replay neutrality

Exact command replay, idempotency replay, and duplicate broker observation
replay do not increment revision.

## Conflict neutrality

Command conflicts, idempotency conflicts, stale commands, and conflicting
broker observations do not increment the aggregate revision unless a separately
accepted lifecycle transition records reconciliation requirement.

## Broker observation concurrency

Broker observations compete on aggregate revision and observation identity.
Duplicates replay; conflicting observations require reconciliation rather than
last-write-wins.

## Cancellation/fill race

Fill observation and cancellation confirmation can race. The first accepted
revision wins. The loser must reload aggregate state and either replay, reject,
or require reconciliation.

## Replacement/fill race

Replacement confirmation and fill observation can race. The first accepted
revision wins. Replacement cannot erase already-filled quantity.

## Reconciliation concurrency

Only one reconciliation transaction may update an aggregate revision at a time.
Stale reconciliation attempts must reload current state and restart analysis.

## Terminal-state protection

Terminal states reject new non-reconciliation/non-failure mutation unless the
lifecycle model explicitly allows it. Terminal protection must be enforced
before broker contact.

## Isolation requirement

The store must provide transactions with uniqueness constraints and either
row-level locking or compare-and-swap semantics strong enough to prevent two
workers from both believing they won the same revision.

## Non-reuse rule

Do not reuse qualification revision, broker version, or database row version as
execution lifecycle revision. They may be stored as supporting facts only.
