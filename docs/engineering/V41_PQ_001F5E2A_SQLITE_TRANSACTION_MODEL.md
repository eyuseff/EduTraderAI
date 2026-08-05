# V41-PQ-001F5E2A SQLite Transaction Model

## Governing rules

- No SQLite transaction may span a broker network call.
- Authoritative writes commit atomically or not at all.
- `BEGIN IMMEDIATE` is required for write transactions.
- Replay and conflicts are revision-neutral.
- No hidden retry loop is allowed.

## Command intake transaction

The future adapter must perform command registration, idempotency reservation, aggregate CAS, and transition append inside one authoritative transaction when a local lifecycle transition is accepted.

Conceptual order:

1. `BEGIN IMMEDIATE`.
2. Load command by `command_id`.
3. If same payload fingerprint exists, return replay.
4. If different payload fingerprint exists, return conflict.
5. Load idempotency key.
6. If same logical fingerprint exists, return replay/pending.
7. If different logical fingerprint exists, return conflict.
8. Insert command.
9. Insert idempotency reservation.
10. CAS aggregate from expected execution revision.
11. Append transition.
12. Persist receipt/failure/approval/reconciliation fact when applicable.
13. Commit.

If any authoritative insert/update fails, the transaction rolls back.

## CAS statement model

```sql
UPDATE execution_aggregates
SET lifecycle_state = :next_state,
    execution_revision = :next_revision,
    updated_at = :updated_at,
    last_transition_id = :transition_record_id,
    last_command_id = :command_id,
    last_idempotency_key = :idempotency_key
WHERE aggregate_id = :aggregate_id
  AND execution_revision = :expected_revision;
```

Exactly one affected row is required. Zero rows means stale or missing aggregate. The adapter must not append a transition or activate any side-effect intent.

## Dispatch boundary

When broker execution is separately authorized in a future slice, dispatch still uses two local transactions around the external broker call:

- Transaction A persists durable dispatch intent and `DISPATCH_PENDING`.
- Broker call occurs outside SQLite transaction.
- Transaction B persists normalized broker result or `OUTCOME_UNKNOWN` / `RECONCILIATION_REQUIRED`.

This design does not authorize that broker call.

## Rollback model

Injected failures must leave no partial command, idempotency, aggregate revision, transition, receipt, failure, approval, or reconciliation write. Commit ambiguity must be resolved through database inspection and, if an external effect may have happened, reconciliation.

## Busy behavior

The proposed initial busy timeout is 200 ms. A timeout before any possible external effect can fail safely as infrastructure contention. A timeout after a possible external effect must preserve ambiguity and require recovery. Automatic retry is prohibited unless a later design proves it cannot duplicate external effects.

## Read transactions

Read-only loading and restart discovery may use ordinary explicit read transactions. Read-only inspection must not mutate state or advance lifecycle.

## Migration transactions

Migrations must be explicit, ordered, checksum-validated, backed up first, and wrapped in transactions where SQLite supports transactional DDL. Failure shuts down startup compatibility rather than recreating the database.
