# V41-PQ-001F5E2A SQLite Migration Model

## Future location

Future implementation should use:

`volcanoes/infrastructure/execution_persistence/sqlite/migrations/`

This directory is not created in this design slice.

## Migration identity

Each migration has:

- ordered `migration_id`;
- descriptive name;
- checksum;
- previous schema version;
- resulting schema version;
- application version;
- applied UTC timestamp;
- safe notes.

## Startup compatibility

Startup must validate:

1. migration table exists;
2. applied migration order is monotonic;
3. checksums match repository-known migrations;
4. current schema version is supported;
5. no unknown future schema is opened by an older application;
6. required tables, indexes, and triggers exist.

## Execution rules

- Back up before migration.
- Wrap migration in a transaction where SQLite supports it.
- Record success only after all statements and validation pass.
- Duplicate ID with same checksum is replay.
- Duplicate ID with different checksum fails.
- Failed migration leaves no false success row.
- No destructive automatic migration.
- No silent database recreation.

## Downgrade policy

Downgrade is not automatic. A downgrade requires explicit operator recovery planning and must preserve command history, idempotency records, revisions, broker references, unknown outcomes, and reconciliation facts.

## Migration tests for F5E2B

Future tests must cover ordering, checksum mismatch, duplicate migration, failed migration rollback, startup compatibility, data preservation, invariant validation, and old-client rejection.
