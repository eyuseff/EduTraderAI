# V41-PQ-001F5E0 Migration and Rollback Plan

## Purpose

Define migration and rollback requirements for future execution persistence.
This is design only.

## Migration requirements

Future durable storage must include:

- schema version table;
- forward migrations;
- rollback migrations where safe;
- irreversible migration marking;
- backup before migration;
- migration checksum;
- startup compatibility check;
- old-client rejection;
- dry-run migration tests;
- migration failure behavior;
- post-migration data validation.

## Startup compatibility

Application startup must refuse execution if schema version is missing,
unsupported, newer than the client, or marked as failed.

## Backup before migration

Every migration that touches execution authority must require a backup or
snapshot. Backup identity and checksum must be recorded.

## Irreversible migrations

Irreversible migrations require explicit operator approval, downgrade
prohibition, and a documented restore-from-backup path.

## Rollback strategy

Permitted rollback:

- disable future persistence integration before broker execution;
- revert repository wiring;
- restore verified backup;
- keep append-only history;
- downgrade only when schema supports it;
- stop execution when schema incompatibility exists.

Forbidden rollback:

- delete command history;
- reset idempotency keys;
- rewrite revisions;
- remove broker references;
- erase unknown outcomes;
- silently reinitialize database;
- treat dry-run results as execution state.

## Backup and restore

Backup and restore must verify:

- aggregate snapshot consistency with transition journal;
- command and idempotency uniqueness;
- broker reference uniqueness;
- receipt/failure fingerprint integrity;
- schema version compatibility;
- no secret-bearing fields.
