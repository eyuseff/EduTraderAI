# V41-PQ-001F5E2A SQLite Integrity and Corruption Handling

## Startup checks

Future adapter startup must validate:

- database path and locality;
- parent permissions;
- SQLite version;
- foreign keys active;
- WAL active;
- busy timeout set;
- schema version compatible;
- migration checksums valid;
- required tables/indexes/triggers present;
- `PRAGMA quick_check`;
- consequential state discovery.

## Routine integrity checks

Routine checks:

- `PRAGMA quick_check`;
- foreign-key check;
- migration checksum validation;
- aggregate revision versus transition history;
- command payload fingerprint consistency;
- idempotency binding consistency;
- broker-reference ownership consistency;
- terminal-state consistency;
- unknown/reconciliation state discovery.

Full maintenance checks:

- `PRAGMA integrity_check`;
- backup restore drill;
- WAL checkpoint health;
- filesystem free-space review.

## Severity model

Critical failures stop authoritative execution. Examples: corruption, FK check failure, migration checksum mismatch, schema incompatibility, database unavailable, read-only filesystem, permission denial, disk full, or WAL configuration failure.

Non-critical warnings may allow read-only inspection but must not authorize new broker effects.

## Corruption response

On corruption or critical inconsistency:

- stop authoritative execution;
- preserve the active database;
- do not rewrite history;
- do not reset revisions;
- do not clear idempotency;
- do not delete broker references;
- do not resubmit orders;
- create a safe diagnostic copy only after future approval;
- require operator intervention and restore/reconciliation procedure.

## Failure classifications

SQLite-specific infrastructure failures should map to storage-neutral results:

- `DATABASE_UNAVAILABLE`;
- `DATABASE_LOCKED`;
- `DATABASE_BUSY_TIMEOUT`;
- `SCHEMA_INCOMPATIBLE`;
- `MIGRATION_REQUIRED`;
- `MIGRATION_FAILED`;
- `INTEGRITY_CHECK_FAILED`;
- `FOREIGN_KEY_CHECK_FAILED`;
- `CORRUPTION_DETECTED`;
- `DISK_FULL`;
- `PERMISSION_DENIED`;
- `READ_ONLY_FILESYSTEM`;
- `WAL_CONFIGURATION_FAILED`;
- `BACKUP_FAILED`;
- `RESTORE_VALIDATION_FAILED`;
- `CAS_CONFLICT`;
- `UNIQUE_CONSTRAINT_CONFLICT`;
- `TRANSACTION_ABORTED`.

Raw SQL exceptions must not leak into application decisions.
