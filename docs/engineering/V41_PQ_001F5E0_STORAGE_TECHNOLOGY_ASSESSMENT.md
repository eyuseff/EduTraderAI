# V41-PQ-001F5E0 Storage Technology Assessment

## Purpose

Assess persistence technologies for future execution durability. This document
selects no implementation and creates no database.

## Scoring legend

High = strong fit, Medium = workable with constraints, Low = insufficient or
high-risk for authoritative execution state.

| Technology | Local single-user | Transactions | Uniqueness | Concurrency | Migration | Operational burden | Future web deployment |
|---|---|---|---|---|---|---|---|
| SQLite | High | High | High | Medium | Medium | Low | Medium |
| PostgreSQL | Medium | High | High | High | High | Medium/High | High |
| JSON/JSONL files | Medium | Low | Low | Low | Low | Low | Low |
| In-memory | High for tests | None durable | Low | Low | None | Low | Low |
| Redis/KV | Medium | Medium | Medium | Medium/High | Medium | Medium | Medium |

## SQLite assessment

Strengths:

- already present for portfolio persistence;
- transactional guarantees;
- uniqueness constraints;
- optimistic concurrency by compare-and-swap;
- WAL support;
- portable local deployment;
- low operational burden.

Conditions if selected:

- single-machine deployment only;
- WAL mode enabled;
- foreign keys enabled;
- explicit migrations;
- transactional repository/unit of work;
- no network filesystem;
- backup procedure;
- corruption handling runbook;
- future PostgreSQL migration path.

Limitations:

- multi-host coordination is not appropriate;
- file locking can be fragile on network filesystems;
- operational monitoring is limited compared with server databases.

## PostgreSQL assessment

Strengths:

- row-level locking;
- strong concurrent worker support;
- mature uniqueness/indexing;
- JSON support;
- migration tooling;
- better future web deployment path.

Costs:

- higher local setup burden;
- credential/operations complexity;
- backup/restore administration;
- overkill for single-process local Paper deployment unless multi-worker
  execution is planned soon.

## JSON/JSONL assessment

JSON and JSONL are useful for evidence and audit exports, but unsuitable as
authoritative execution state because uniqueness, atomic multi-record commits,
optimistic concurrency, and crash consistency are hard to guarantee.

## In-memory assessment

In-memory stores are excellent for deterministic contract tests and fake unit
of work behavior. They are restart-unsafe and not production execution state.

## Redis/key-value assessment

Redis can provide atomic operations and leases, but durable relational history,
migrations, backup semantics, and source-of-truth clarity require extra design.
It may be useful as a future coordination adjunct, not the initial
authoritative execution journal.

## Technology decision

Decision: `REQUIRE_TECHNOLOGY_SPIKE`.

Rationale: SQLite appears suitable for initial single-machine Paper execution
under strict conditions, while PostgreSQL is more appropriate for future
multi-worker/multi-host deployments. Because broker execution carries duplicate
submission risk, the next step should prove SQLite transaction, WAL,
uniqueness, backup, restart, and concurrent-process behavior in a bounded
technology spike before selecting it.

## Spike requirements

The spike must test:

- command uniqueness;
- idempotency uniqueness;
- aggregate revision compare-and-swap;
- transition journal append plus snapshot update atomicity;
- duplicate process contention;
- crash after `DISPATCH_PENDING`;
- rollback on mid-transaction failure;
- backup/restore;
- migration version checks;
- network-filesystem prohibition documentation.
