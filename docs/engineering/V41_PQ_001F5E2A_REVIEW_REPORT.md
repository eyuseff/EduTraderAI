# V41-PQ-001F5E2A Review Report

## 1. Executive summary

F5E2A completes a documentation-only SQLite durable adapter design. Project
Sentinel reviewed ADR-008 and accepted it. F5E2B may implement only the SQLite
schema and migration foundation; repositories, runtime wiring, and broker
execution remain unauthorized.

## 2. Starting baseline

Starting HEAD: `f9e6e437a78d97719d3db9093d22b2314daa6a34`.

Baseline: 1,935 tests passing, 87 architecture tests passing, 86.5% coverage, ADR-004 through ADR-007 Accepted, F5E1A contracts implemented, F5E1B in-memory adapter implemented, F5E spike completed, broker execution `NOT_AUTHORIZED`.

## 3. Scope

SQLite adapter architecture, schema design, transaction model, locking model, migration model, backup/restore, integrity, corruption handling, security, permissions, PostgreSQL migration triggers, and implementation sequencing.

## 4. Exclusions

No production SQLite code, SQL deployment, migration runner, database file, runtime wiring, broker port, broker adapter, broker call, simulator integration, event publisher, metrics, logging, UI, API, CLI, dependency, configuration, Paper trading enablement, or Live behavior.

## 5. Spike evidence used

SQLite 3.50.4 passed 30/30 isolated spike scenarios. PostgreSQL runtime was unavailable and statically assessed. Storage decision remains `SELECT_SQLITE_WITH_MANDATORY_POSTGRESQL_MIGRATION_TRIGGER`.

## 6. Proposed adapter architecture

Future adapter under `volcanoes/infrastructure/execution_persistence/sqlite/` implementing F5E1A ports and preserving storage-neutral contracts.

## 7. Deployment envelope

One machine, local filesystem, one application authority, one active write coordinator, no network/shared/cloud-synced filesystem, no multi-host, no active-active.

## 8. Database ownership

Execution persistence records only. Broker truth and simulator state remain outside the database.

## 9. Database path model

Approved local application data directory outside repo/Git/state/build/temp/cloud/network paths, validated before use.

## 10. Connection configuration

Foreign keys ON, WAL, bounded busy timeout, explicit transactions, extension loading disabled, deterministic rows.

## 11. WAL model

WAL required; manual WAL/SHM manipulation prohibited; checkpoint policy deferred to implementation validation.

## 12. Synchronous mode

`synchronous = FULL` proposed initially for safety-first crash durability.

## 13. Busy timeout

Initial proposal: 200 ms, bounded, visible, not a hidden retry loop.

## 14. Transaction model

`BEGIN IMMEDIATE` for authoritative writes; broker calls never inside local transaction.

## 15. Schema inventory

Ten tables: aggregates, commands, idempotency, transitions, broker references, receipts, failures, approvals, reconciliations, migrations.

## 16. Aggregate schema

`ExecutionAggregateRecord` materialized snapshot with aggregate ID, correlation ID, lifecycle state, execution revision, quantities, flags, last references, timestamps, mode, schema version, and fingerprint. CAS authoritative.

## 17. Command schema

`ExecutionCommandRecord` immutable command ID, aggregate/correlation/idempotency IDs, operation, expected revision, canonical payload, approval/policy fingerprints, outcome, timestamp, mode, schema version, fingerprint.

## 18. Idempotency schema

`ExecutionIdempotencyRecord` permanent key to logical fingerprint binding, command/aggregate refs, status, result fingerprint, timestamps, conflict flag, mode, schema version, fingerprint.

## 19. Transition journal schema

`ExecutionTransitionRecord` append-only accepted transition with previous/next revisions, states, input identity, intents, safe reason code, optional broker/receipt/failure refs, timestamp, mode, schema version, fingerprint.

## 20. Broker-reference schema

`ExecutionBrokerReferenceRecord` normalized broker reference primary key, aggregate/command refs, adapter identity, status, first/last seen, active flag, replacement ref, mode, schema version, fingerprint.

## 21. Receipt schema

Immutable normalized `PaperExecutionReceipt` record by fingerprint.

## 22. Failure schema

Immutable normalized `PaperExecutionFailure` record by fingerprint.

## 23. Approval schema

`ExecutionApprovalRecord` by approval fingerprint with safe approver reference, bound fingerprint, expiry/revocation refs, timestamps, mode, schema version, fingerprint.

## 24. Reconciliation schema

`ExecutionReconciliationRecord` append-only reconciliation facts with starting revision/state, broker observation refs, classification, result refs, operator/unresolved flags, safe reason code.

## 25. Migration schema

`schema_migrations` with migration ID, name, checksum, versions, application version, applied timestamp, and safe notes.

## 26. Constraints

Primary keys, FKs, enum checks, boolean checks, revision non-negative, `next_revision = previous_revision + 1`, unique `(aggregate_id, next_revision)`, command fingerprint immutability, idempotency fingerprint immutability, broker-reference ownership.

## 27. Indexes

Lifecycle, consequential state, aggregate command history, idempotency aggregate, transition aggregate/revision, broker active reference, unresolved reconciliation, and migration version indexes.

## 28. Append-only protections

Recommend SQLite triggers rejecting update/delete on transition, receipt, failure, approval, and reconciliation history tables where immutability is required.

## 29. CAS model

Exact `aggregate_id` plus `execution_revision` update; exactly one row affected; zero rows fail closed.

## 30. Startup validation

Path, local filesystem, permissions, SQLite version, PRAGMAs, schema/migration checksums, required objects, quick check, invariants, consequential state discovery.

## 31. Integrity checks

Quick check, full integrity check, foreign-key check, migration checksum, revision/journal consistency, fingerprint consistency, idempotency consistency, broker-reference ownership, terminal-state consistency.

## 32. Backup

SQLite backup API or approved WAL-safe method, separate local directory, metadata, checksums, verification, no simple live copy.

## 33. Restore

Maintenance mode, stopped execution authority, preserve current database, restore to new path, validate checksum/schema/integrity/FKs/invariants, operator approval.

## 34. Corruption handling

Stop authoritative execution, preserve database, no history rewrite, no idempotency reset, no broker resubmission, operator intervention.

## 35. WAL checkpoints

WAL required; PASSIVE is safe routine default, FULL may be maintenance, RESTART/TRUNCATE only under controlled maintenance after backup/validation.

## 36. Security and permissions

Least-privilege local files, no world-readable DB/WAL/SHM/backups, no secrets, no raw broker payloads, encryption deferred.

## 37. Retention

Retention categories defined; final periods deferred. Authoritative lifecycle history not silently deleted.

## 38. PostgreSQL triggers

Mandatory before multi-host, multiple execution workers, remote shared DB, high write concurrency, public multi-user, managed web, network filesystem, failover, operational backup requirements beyond local file model, or SQLite envelope breach.

## 39. PostgreSQL migration path

Preserve identities, revisions, idempotency, transition order, broker references, fingerprints, timestamps, and reconciliation states. Dual-write prohibited unless separately designed.

## 40. Failure mapping

SQLite infrastructure failures map to safe storage-neutral results such as database unavailable, locked, busy timeout, schema incompatible, migration failed, integrity failed, corruption, disk full, permission denied, WAL failed, backup/restore failed, CAS conflict, unique conflict, and transaction aborted.

## 41. Tests for future implementation

Schema creation, migrations, checksum mismatch, PRAGMAs, replay/conflict, idempotency races, CAS, rollback, append-only triggers, broker-reference uniqueness, restart discovery, backup/restore, corruption, lock contention, no production path use, no broker imports.

## 42. Risks

Filesystem classification, WAL misuse, local lock contention, backup discipline, restore operator error, corruption response, premature multi-process use, accidental runtime wiring.

## 43. Accepted decisions

SQLite local single-machine proposal, WAL required, foreign keys required, `synchronous = FULL`, `BEGIN IMMEDIATE` writes, CAS authoritative, append-only triggers recommended, PostgreSQL triggers mandatory.

## 44. Conditional decisions

200 ms busy timeout subject to validation; read-only local inspection subject to non-writing enforcement; checkpoint details subject to implementation validation.

## 45. Deferred decisions

Final path/configuration, encryption, retention periods, backup cadence, restore UX, production metrics, multi-process writer support, PostgreSQL migration implementation.

## 46. Rejected alternatives

Immediate runtime wiring, broker execution, JSON authoritative store, portfolio table reuse, network filesystem SQLite, multi-host SQLite, silent DB recreation, hidden retries.

## 47. ADR-008 readiness

ADR-008 accepted by Sentinel review.

## 48. F5E2B readiness

F5E2B is `READY_FOR_IMPLEMENTATION` for schema, migration, connection
bootstrap, PRAGMA verification, startup validation, quick-check/FK-check
support, and isolated temporary-database tests only.

## 49. Next recommended slice

`V41-PQ-001F5E2B — SQLite Schema and Migration Foundation`.

## 50. Explicit non-implementation statement

F5E2A is design only. No SQLite production code, schema deployment, migration runner, database file, runtime wiring, broker port, broker adapter, dependency, configuration, UI, API, or CLI was added.

## 51. Explicit non-execution statement

No broker was called, no execution authority was added, no runtime action was executed, broker execution remains prohibited, and V41-PQ-001 remains incomplete.

## Review decision

`ACCEPTED`.

Conditions:

- Sentinel must review ADR-008 before implementation.
- SQLite remains limited to local single-machine Paper envelope.
- PostgreSQL triggers remain mandatory.
- Broker execution remains separately unauthorized.

Critical findings: none.

Major findings: none.

Minor findings: F5E2B should validate the 200 ms busy timeout and trigger-based append-only protections.

Observations: PostgreSQL remains architecturally stronger for multi-worker/multi-host operation even though SQLite is the proposed initial local backend.
