# V41-PQ-001F5E2A SQLite Adapter Architecture

## Summary

This document designs, but does not implement, the production SQLite durable execution adapter proposed by ADR-008. The adapter would live below the existing storage-neutral F5E1A persistence ports and would preserve F5E1B behavior with SQLite as the authoritative local store.

## Architecture boundary

Future package, not created in this slice:

`volcanoes/infrastructure/execution_persistence/sqlite/`

The future package may contain connection management, schema SQL, migrations, repository adapters, unit-of-work implementation, backup/restore utilities, and integrity validation. It must not be imported by Streamlit, scanner, broker adapters, or runtime execution until separately authorized.

## Ownership

SQLite owns only execution persistence records:

- `ExecutionAggregateRecord`;
- `ExecutionCommandRecord`;
- `ExecutionIdempotencyRecord`;
- `ExecutionTransitionRecord`;
- `ExecutionBrokerReferenceRecord`;
- `ExecutionReceiptRecord`;
- `ExecutionFailureRecord`;
- `ExecutionApprovalRecord`;
- `ExecutionReconciliationRecord`.

It does not own broker truth, scanner decisions, portfolio persistence, simulator state, validation evidence, or UI state.

## Supported deployment envelope

Initial supported model is intentionally narrow:

- one machine;
- one local filesystem;
- one active EMERS application deployment authority;
- one active execution write coordinator;
- one SQLite execution database;
- multiple local adapter connections only as needed;
- read-only inspection tooling allowed only when it cannot write;
- backup tooling may open a second connection through the SQLite backup API;
- restore requires maintenance mode and stopped execution authority.

Prohibited:

- multiple active execution writers;
- multiple application hosts;
- network filesystems;
- cloud-synced folders;
- active-active deployment;
- shared remote database access.

## Database location model

The future database path must be outside the repository and outside `state/`. It must be in an approved local application data directory with validated parent permissions. The adapter must reject paths under source, Git, build, temporary spike directories, cloud-sync folders, network shares, or symlink paths whose resolved target violates these rules.

No final user-specific path or environment variable is introduced in this design slice.

## Connection model

Each connection must:

- enable and verify foreign keys;
- enable and verify WAL;
- set a bounded busy timeout;
- disable extension loading;
- use explicit transactions;
- avoid shared-cache correctness assumptions;
- use deterministic row access;
- preserve canonical text fields exactly.

Proposed initial settings:

- `PRAGMA foreign_keys = ON`;
- `PRAGMA journal_mode = WAL`;
- `PRAGMA synchronous = FULL` for the initial safety-first adapter;
- `PRAGMA busy_timeout = 200`;
- no automatic retry after timeout.

`synchronous = FULL` is selected over `NORMAL` for the first production design because correctness and crash durability matter more than speed. A later validation slice may reassess it.

## Transaction model

Authoritative writes use `BEGIN IMMEDIATE`. Reads may use ordinary `BEGIN`. Migrations use explicit transactions when SQLite allows. `BEGIN EXCLUSIVE` is reserved for maintenance-only operations if future validation requires it.

No transaction may include a broker network call.

## Repository composition

The future adapter should implement the existing ports:

- `ExecutionAggregateRepository`;
- `ExecutionCommandRepository`;
- `ExecutionIdempotencyRepository`;
- `ExecutionTransitionJournal`;
- `ExecutionBrokerReferenceRepository`;
- `ExecutionReceiptRepository`;
- `ExecutionFailureRepository`;
- `ExecutionApprovalRepository`;
- `ExecutionReconciliationRepository`;
- `ExecutionRestartDiscoveryRepository`;
- `ExecutionUnitOfWork`;
- `ExecutionPersistenceSession`.

## Failure boundary

SQLite-specific failures must be normalized into storage-neutral persistence results and safe errors. Raw SQL errors must not leak into application decisions.

## Non-implementation statement

This file adds no SQLite code, schema, migration runner, database file, runtime wiring, broker port, broker adapter, metrics, event publisher, UI, API, CLI, or execution authority.
