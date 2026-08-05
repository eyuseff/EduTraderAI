# Project Sentinel Review: ADR-008 SQLite Execution Durable Adapter

## Review identity

Review: Sentinel ADR-008 SQLite Execution Durable Adapter.

Date: 2026-08-05.

Repository branch: `feature/edutrader-v4.1`.

Starting HEAD: `d4f0f3b84b6bcfc6b5cc03d6e3759d225d337485`.

## Review outcome

APPROVED.

ADR-008 final status: Accepted.

F5E2B readiness: `READY_FOR_IMPLEMENTATION`.

F5E2C readiness: `NOT_YET_AUTHORIZED`.

Broker-execution readiness: `NOT_AUTHORIZED`.

## Scope reviewed

- `docs/adr/ADR-008-SQLITE-EXECUTION-DURABLE-ADAPTER.md`.
- F5E2A SQLite adapter architecture, schema, transaction, concurrency, migration, backup/restore, integrity, security, PostgreSQL trigger, implementation-plan, and review-report documents.
- ADR-007 and Sentinel ADR-007 review/audit documents.
- F5E durability spike SQLite, concurrency, migration/backup, and final recommendation documents.
- F5E1A persistence contracts and F5E1B in-memory reference implementation.
- Isolated spike package under `spikes/execution_durability/`.

## Scope explicitly excluded

No production SQLite adapter, sqlite3 code, SQL schema file, migration runner, database file, repository implementation, unit-of-work implementation, runtime wiring, broker port, broker adapter, broker call, backup tooling, restore tooling, event publishing, metrics, production logging, UI, API, CLI, Paper trading enablement, or Live behavior was implemented or authorized by this review.

## Current implementation facts

F5E1A defines storage-neutral immutable records, repository results, repository ports, and unit-of-work/session ports. F5E1B implements deterministic process-local in-memory behavior only. The durability spike executed 30/30 SQLite scenarios successfully with synthetic data. No production durable adapter exists.

## Mandatory review questions

All 74 mandatory review questions passed. Summary:

| Range | Result | Summary |
|---|---|---|
| 1-10 | PASS | Deployment envelope, single-machine rule, local filesystem, path, symlink, and permissions are explicit. |
| 11-18 | PASS | PRAGMAs, WAL, foreign keys, synchronous FULL, busy timeout, no hidden retry, and transaction modes are explicit. |
| 19-26 | PASS | F5E1A records map to tables, identities are stable text, decimals/timestamps are canonical, and CAS is exact. |
| 27-36 | PASS | Command immutability, idempotency binding, reservation timing, append-only journal, replay/conflict exclusion, and triggers are safe. |
| 37-41 | PASS | Broker references, receipts, failures, approvals, and reconciliations are constrained and safe. |
| 42-53 | PASS | Migrations, startup validation, integrity checks, corruption handling, and blind-resubmission prohibition are fail-closed. |
| 54-67 | PASS | WAL-safe backup, restore, WAL/SHM protection, permissions, secret exclusion, encryption deferral, and retention deferral are explicit. |
| 68-74 | PASS | PostgreSQL migration triggers, migration-path preservation, dual-write rejection, F5E2B scope, and broker-execution prohibition are explicit. |

## Final deployment envelope

Initial SQLite support is one machine, one application process owning execution writes, one active execution authority, one active write coordinator, local filesystem only, no concurrent execution worker process, and read-only/backup/maintenance connections only under explicit procedures.

## Final connection configuration

Required: `foreign_keys = ON`, `journal_mode = WAL`, `synchronous = FULL`, bounded busy timeout, explicit transactions, deterministic row handling, extension loading disabled, UTF-8 text, no database default current timestamp, no shared-cache correctness assumption.

## Final schema decision

Tables: `execution_aggregates`, `execution_commands`, `execution_idempotency`, `execution_transitions`, `execution_broker_references`, `execution_receipts`, `execution_failures`, `execution_approvals`, `execution_reconciliations`, and `schema_migrations`.

Decimal representation: canonical decimal `TEXT`.

Timestamp representation: UTC `TEXT` in `YYYY-MM-DDTHH:MM:SS.ffffffZ`.

## Final transaction and CAS decision

Authoritative writes use `BEGIN IMMEDIATE`. CAS requires exact aggregate ID and execution revision with exactly one affected row. Zero rows fail closed as stale/not-found. No broker call may occur inside a transaction.

## Final append-only decision

Denial triggers are required for commands, transitions, receipts, failures, approvals, reconciliations, and migrations. Idempotency and broker-reference rows allow only controlled status/observation updates under exact predicates.

## Final backup/restore/corruption decision

Backups use SQLite backup API or an approved WAL-safe method. Restore requires maintenance mode, stopped execution authority, validation, and operator activation approval. Critical integrity failures block authoritative execution and prohibit automatic repair or blind broker resubmission.

## Final PostgreSQL migration decision

PostgreSQL migration is mandatory before multiple application hosts, multiple active execution workers, shared remote DB, network filesystem, high write concurrency, public multi-user deployment, managed web service, failover/high availability, centralized DB administration, backup/recovery needs beyond local file model, or validated SQLite envelope breach.

## F5E2B authorization

F5E2B may implement only:

- isolated SQLite infrastructure package;
- schema SQL;
- migration metadata;
- migration runner;
- connection bootstrap;
- PRAGMA verification;
- schema compatibility validation;
- table/index/trigger validation;
- quick-check and foreign-key-check support;
- isolated temporary-database tests.

F5E2B must not implement repositories, F5E1A port implementation, application services, runtime wiring, brokers, production database path activation, Paper trading, or Live behavior.

## Findings disposition

Critical findings: none.

Major findings: none.

Minor findings: 5 closed.

Observations: 4 deferred and non-blocking.

## Approval decision

ADR-008 is Accepted.

F5E2B is ready for implementation within the scope above.

F5E2C is not yet authorized.

Broker execution remains `NOT_AUTHORIZED`.
