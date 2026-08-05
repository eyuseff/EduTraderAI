# Sentinel ADR-008 Migration Audit

## Audit result

PASS.

The migration model is safe for F5E2B schema and migration foundation.

## Required migration metadata

- `migration_id`;
- `migration_name`;
- checksum;
- applied UTC timestamp;
- application version;
- previous schema version;
- resulting schema version;
- success marker or applied-only row semantics;
- optional safe notes.

## Migration rules

- Migration IDs are ordered and unique.
- Checksums are immutable.
- Duplicate ID with same checksum is replay.
- Duplicate ID with different checksum fails closed.
- Failed migration must not write a success record.
- Backup is required before migration.
- Post-migration validation is required.
- Unknown newer schemas are rejected at startup.
- Silent database recreation is prohibited.
- Destructive automatic migration is prohibited.

## Transaction safety

F5E2B must test transaction wrapping for the supported SQLite version and for every initial DDL statement it introduces. If any DDL cannot be safely rolled back, the migration plan must explicitly fail closed and document the recovery procedure.

## Downgrade policy

Automatic downgrade is rejected. Downgrade requires explicit operator recovery planning and must preserve command history, idempotency, revisions, broker references, unknown outcomes, and reconciliation records.

## Future package location

`volcanoes/infrastructure/execution_persistence/sqlite/`

The package must remain disconnected from runtime composition in F5E2B.

## Audit conclusion

F5E2B may implement migration metadata, migration runner, startup compatibility validation, and isolated temporary-database migration tests only.
