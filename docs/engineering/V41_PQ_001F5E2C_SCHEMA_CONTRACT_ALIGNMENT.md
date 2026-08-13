# F5E2C Schema-Contract Alignment

## Purpose

F5E2C corrects the durable SQLite schema so its persisted vocabulary and fact
shape match the immutable application persistence contracts. It is a storage
schema correction only: it does not alter application contracts, add a
repository or unit-of-work implementation, perform a runtime migration, or
authorize broker activity.

## Authoritative contracts

Application enums and record contracts remain the source of truth. The v002
migration maps the supported v001 values as follows:

| v001 | Current contract |
| --- | --- |
| `REGISTERED` | `PENDING` |
| `REPLAY` | `REPLAYED` |
| `CONFLICT` | `CONFLICTED` |
| `REJECTED` | `REJECTED` |
| `RESERVED` | `RESERVED` |
| `RESOLVED` | `COMPLETED` |
| `UNKNOWN` | `RECONCILIATION_REQUIRED` |
| `NOT_REPLAY` | `NONE` |

`REPLAY_SUPPRESSED`, unsupported legacy enum values, and any populated legacy
receipt or failure table abort the migration. This is deliberate fail-closed
behavior: the v001 fact tables cannot represent all mandatory current receipt
or failure attributes without loss.

## Migration decision

`v001_initial_schema.sql` remains immutable. `v002_contract_alignment.sql` is
an irreversible, transactional corrective migration registered after v001. It
rebuilds only the affected tables, preserves existing identifiers,
fingerprints, timestamps, indexes, append-only triggers, and foreign-key
relationships, and runs `foreign_key_check` before recording success.
Every rebuilt timestamp keeps v001's canonical UTC text constraint.

The runner rejects a caller-owned transaction before any migration statement is
executed. It validates complete SQLite statements before beginning its own
`BEGIN IMMEDIATE` transaction, executes those statements without
`executescript()`, and rolls back only that migration-owned transaction on a
schema or data-copy failure. Migration metadata is inserted in the same
transaction as the schema change.

The aggregate foreign keys on commands and idempotency reservations are
`DEFERRABLE INITIALLY DEFERRED`. This supports the documented command →
idempotency → aggregate write ordering while retaining all other foreign-key
checks at their normal boundary. A missing aggregate therefore fails at commit.

## Reference-adapter alignment

The process-local in-memory transition journal now enforces the same three
identities as SQLite:

1. `transition_record_id` permits exact-content replay only.
2. `(aggregate_id, next_revision)` is unique.
3. `(aggregate_id, transition_id)` is unique.

Collision outcomes use the existing deterministic transition-result contract;
no public persistence interface changes were made.

## F5E2C phase boundary

This phase adds the migration, schema metadata, focused contract tests, and
in-memory reference alignment only. It does not implement the F5E2C durable
repository or unit of work. Phase 1 validation is complete: Ruff, Black, and MyPy passed, and 221 tests passed (62 focused SQLite, 72 in-memory/ports, and 87 architecture); Phase 2 remains unimplemented and requires separate authorization.
