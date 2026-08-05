# ADR-008: SQLite Execution Durable Adapter

## 1. Title

SQLite Execution Durable Adapter for initial local Paper execution persistence.

## 2. Status

Proposed.

ADR-008 is not Accepted. It requires separate Sentinel review before implementation authorization.

## 3. Date

2026-08-05.

## 4. Context

ADR-007 is Accepted and defines the execution persistence and idempotency architecture. F5E1A implements storage-neutral persistence contracts and unit-of-work ports. F5E1B implements a deterministic process-local in-memory reference adapter. The F5E durability spike compared SQLite and PostgreSQL. SQLite executed all 30 isolated synthetic scenarios successfully; PostgreSQL runtime execution was unavailable and was assessed statically.

## 5. Problem

EMERS Trade Paper execution needs durable command identity, idempotency, lifecycle revision, transition history, broker-reference observation, receipt, failure, approval, and reconciliation persistence before broker execution can be separately authorized. The initial durable backend must fit local single-machine Paper deployment without weakening ADR-007 semantics.

## 6. Decision proposal

Propose a production SQLite durable adapter that implements the existing F5E1A ports without changing the storage-neutral contracts. The adapter will be limited to initial local single-machine Paper deployment and will use database constraints, explicit transactions, WAL, foreign keys, compare-and-swap updates, append-only journal protections, schema migrations, startup validation, backup/restore validation, and fail-closed integrity checks.

This ADR alone implements no database.

## 7. Relationship to ADR-007

ADR-008 is subordinate to ADR-007. It does not change the accepted source-of-truth model: command record, aggregate snapshot, transition journal, normalized broker observations, reconciliation records, and supporting evidence. It preserves the ADR-007 rule that no local transaction may span an external broker network call.

## 8. Relationship to F5E spike

The spike selected `SELECT_SQLITE_WITH_MANDATORY_POSTGRESQL_MIGRATION_TRIGGER`. SQLite is therefore proposed only under the spike’s deployment conditions. PostgreSQL remains the required migration target when the operating envelope exceeds validated local SQLite constraints.

## 9. Deployment model

Supported initial model:

- one machine;
- local filesystem;
- one active EMERS application deployment authority;
- one SQLite execution database;
- one active write coordinator;
- multiple local connections only for the adapter, backup, validation, or read-only inspection under the supported local process model;
- no shared network drive;
- no NFS;
- no SMB;
- no cloud-synced folder;
- no remote filesystem abstraction;
- no multi-host active execution;
- no active-active application deployment.

## 10. Single-machine restriction

SQLite execution persistence is proposed only for one local machine. Any multi-host requirement triggers PostgreSQL migration review before expansion.

## 11. Single application authority

Only one application deployment authority may issue authoritative execution writes. Process-local locks may reduce local contention but are not authoritative. Database constraints, transactions, and CAS remain authoritative.

## 12. Database ownership

The future adapter owns only execution persistence records. It does not own broker truth, portfolio state, scanner state, qualification state, validation evidence, simulator state, UI state, or audit/event delivery.

## 13. Database file location

The future database must live in an approved local application data directory outside the source tree, outside Git, outside `state/`, outside `state/simulated_broker.json`, outside temporary build paths, outside cloud-synced folders, and outside shared/network folders. The final path will be provided only by a future approved configuration mechanism.

## 14. Local filesystem requirement

The adapter must validate that the active database path is local, writable by the application identity, and not an unsupported symlink or network mount. If locality cannot be proven, execution authority fails closed.

## 15. Network filesystem prohibition

SQLite execution persistence is not approved on NFS, SMB, cloud-synced directories, network shares, or remote filesystem abstractions. A proposal to use any of these is a mandatory PostgreSQL migration trigger.

## 16. Connection configuration

Every connection must initialize and verify:

- `PRAGMA foreign_keys = ON`;
- `PRAGMA journal_mode = WAL`;
- explicit `busy_timeout`;
- explicit transaction boundaries;
- `row_factory` set to deterministic named/row access;
- UTF-8 text assumptions;
- extension loading disabled;
- no shared-cache reliance;
- connection timeout configured;
- no credentials or secrets in connection logs.

## 17. WAL mode

WAL mode is mandatory. Failure to enter or verify WAL mode is fatal to execution persistence startup.

## 18. Foreign keys

Foreign keys are mandatory on every connection. Startup must verify they are active, and tests must prove FK violations roll back all authoritative writes.

## 19. Busy timeout

The proposed initial busy timeout is 200 ms, matching the spike’s local contention evidence. The value is a future validated constant, not a hidden retry loop. Lock contention after timeout must surface as a normalized infrastructure outcome.

## 20. Transaction mode

Authoritative write transactions must use `BEGIN IMMEDIATE` so the write reservation is acquired before command/idempotency/CAS decisions are finalized. Read transactions may use ordinary `BEGIN`. Schema migrations must run in explicit transactions when SQLite permits. `BEGIN EXCLUSIVE` is reserved for maintenance-only operations if later justified.

## 21. Command uniqueness

`execution_commands.command_id` is primary key. A command ID permanently binds to one canonical payload fingerprint. Same command plus same fingerprint is replay. Same command plus different fingerprint is conflict. No broker call may occur from a command conflict.

## 22. Idempotency uniqueness

`execution_idempotency.idempotency_key` is primary key and permanently binds to one logical operation fingerprint. Same key plus same logical fingerprint is replay or pending-result observation. Same key plus different logical fingerprint is conflict. Keys are not silently reused or expired while external effects might exist.

## 23. Aggregate CAS

Aggregate updates use exact execution revision CAS:

```sql
UPDATE execution_aggregates
SET lifecycle_state = ?,
    execution_revision = ?,
    updated_at = ?,
    last_transition_id = ?
WHERE aggregate_id = ?
  AND execution_revision = ?;
```

Exactly one affected row is required. Zero rows means stale/not-found and must prevent journal append and external-effect activation.

## 24. Transition journal

`execution_transitions` is append-only. Each accepted transition has unique identity and unique `(aggregate_id, next_revision)`. `next_revision = previous_revision + 1` is required. Replay records are not appended as authoritative transitions.

## 25. Broker-reference uniqueness

`execution_broker_references.broker_reference` is primary key. One normalized broker reference maps to one authoritative aggregate. Active ownership cannot silently change. Replacement continuity is explicit via `replaced_by_reference`.

## 26. Receipt/failure/approval/reconciliation storage

Receipts, failures, approvals, and reconciliations are immutable or append-only safe fact records. They store normalized safe fields and fingerprints, never raw broker objects, credentials, callbacks, authorization headers, personal data, or raw exception stacks.

## 27. Schema versioning

Every table includes a `schema_version` or equivalent record schema version. Database-level schema version is tracked through `schema_migrations`.

## 28. Migration checksums

Every migration has immutable ID, name, checksum, previous schema version, resulting schema version, application version, and applied timestamp. Duplicate migration ID with a different checksum fails startup/migration.

## 29. Startup compatibility

Startup validates path, permissions, SQLite version, WAL, foreign keys, busy timeout, schema version, migration checksums, required tables/indexes/triggers, `quick_check`, execution invariants, and consequential states. Critical failure refuses execution.

## 30. Integrity checks

Routine startup uses `PRAGMA quick_check`. Maintenance uses full `PRAGMA integrity_check` and `PRAGMA foreign_key_check`. Execution invariants compare aggregate revision/history, command fingerprints, idempotency bindings, broker-reference ownership, terminal flags, and consequential states.

## 31. Backup

Backups use the SQLite backup API or an approved WAL-safe process. Backups go to a separate local directory, include metadata and checksums, and are verified after completion. Simple live file copy is not approved.

## 32. Restore validation

Restore requires maintenance mode, stopped execution authority, preservation of the current database, checksum verification, schema validation, `quick_check`, `integrity_check`, `foreign_key_check`, execution invariant checks, and operator approval before replacement.

## 33. Corruption handling

On corruption or critical inconsistency, the adapter must stop authoritative execution, preserve the database, avoid history rewrite, avoid idempotency clearing, avoid broker resubmission, and require operator recovery.

## 34. Rollback

Rollback may disable future SQLite integration before broker execution, restore a validated backup, or revert wiring. Rollback must not delete command history, reset revisions, clear idempotency, remove broker references, erase unknown outcomes, or silently recreate the database.

## 35. Security and file permissions

Database, WAL, SHM, and backup files must use least-privilege local permissions and must not be world-readable. The database stores no raw secrets. SQL logging with sensitive values is prohibited. Database encryption is not implemented by this ADR and remains deferred.

## 36. Retention

Command records, idempotency records, transition history, broker references, receipts, failures, approvals, reconciliations, backups, and migration history have distinct retention categories. Final retention periods are deferred to legal, privacy, operational, and commercialization review.

## 37. Operational monitoring

Future implementation must expose presentation-neutral health for schema compatibility, WAL status, last backup, integrity status, consequential states, lock failures, disk-space risk, and migration status. This ADR adds no metrics implementation.

## 38. PostgreSQL migration triggers

PostgreSQL migration becomes mandatory before:

- multiple application hosts;
- multiple active execution workers;
- shared remote database access;
- high write concurrency;
- public multi-user deployment;
- managed web service deployment;
- network filesystem use;
- availability/failover requirements;
- operational backup needs exceeding local file backup;
- concurrency evidence showing SQLite limitations;
- database size or maintenance burden exceeding the validated envelope;
- remote operations requiring centralized database administration.

## 39. Consequences

The proposal gives a narrow durable path for local Paper execution while preserving a PostgreSQL migration boundary. It adds migration, backup, integrity, and file-permission obligations before any runtime use.

## 40. Risks

Risks include lock contention, disk-full failures, filesystem misclassification, WAL misuse, restore operator error, stale schema, corruption, insufficient backup discipline, and accidental expansion beyond the single-machine envelope.

## 41. Alternatives

Alternatives considered: immediate PostgreSQL, retain in-memory only, JSON/JSONL authoritative files, reuse portfolio SQLite tables, full event sourcing, or durable adapter deferral.

## 42. Rejected alternatives

In-memory and JSON/JSONL are not restart/concurrency safe. Portfolio tables do not own execution facts. Full event sourcing is more complex than needed now. Immediate PostgreSQL has stronger scale properties but higher local operational burden and lacks local runtime evidence in this repository.

## 43. Deferred decisions

Deferred: final database path, final configuration surface, encryption mechanism, retention periods, maintenance tooling UX, backup schedule, restore tooling, PostgreSQL migration implementation, multi-process writer support, and production metrics.

## 44. Implementation sequence

Recommended sequence:

1. Sentinel ADR-008 review.
2. `V41-PQ-001F5E2B — SQLite Schema and Migration Foundation`.
3. `V41-PQ-001F5E2C — Transactional SQLite Repository Adapter`.
4. `V41-PQ-001F5E2D — SQLite Durability, Recovery, Backup, and Concurrency Validation`.
5. Later transactional execution application service only after durable adapter validation and separate authorization.

## 45. Non-execution statement

ADR-008 is design only. It implements no SQLite adapter, deploys no schema, creates no migration runner, creates no database file, wires no runtime persistence, adds no broker port, adds no broker adapter, calls no broker, authorizes no execution, enables no Paper trading, and enables no Live behavior. Broker execution remains `NOT_AUTHORIZED`.
