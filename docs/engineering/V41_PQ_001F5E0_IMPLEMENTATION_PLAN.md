# V41-PQ-001F5E0 Implementation Plan

## Purpose

Define the safe sequence after the F5E0 architecture review. This plan
authorizes no implementation by itself.

## Recommended sequence

### V41-PQ-001F5E-SPIKE — Storage Technology Spike

Purpose: prove whether SQLite is safe enough for initial single-machine Paper
execution under explicit conditions.

Scope:

- prototype isolated test schema;
- command uniqueness;
- idempotency uniqueness;
- aggregate revision compare-and-swap;
- append transition plus snapshot update atomicity;
- two-process contention test;
- rollback on failure;
- backup/restore proof;
- migration version proof.

No broker, no runtime wiring.

### V41-PQ-001F5E1 — Persistence Ports and In-Memory Contract Foundation

Scope:

- application-layer ports;
- unit-of-work contracts;
- deterministic in-memory implementation;
- repository contract tests;
- no durable database;
- no broker.

Potential ports:

- `ExecutionUnitOfWork`;
- `ExecutionAggregateRepository`;
- `ExecutionCommandRepository`;
- `ExecutionIdempotencyRepository`;
- `ExecutionTransitionJournal`;
- `ExecutionReceiptRepository`;
- `ExecutionFailureRepository`;
- `ExecutionReconciliationRepository`.

### V41-PQ-001F5E2 — Selected Durable Storage Adapter

Scope:

- selected database schema;
- migrations;
- transactional repositories;
- uniqueness constraints;
- optimistic concurrency;
- restart-safe idempotency;
- no broker.

### V41-PQ-001F5E3 — Crash-Recovery and Concurrency Validation

Scope:

- process restart tests;
- multi-process conflict tests;
- migration tests;
- backup/restore tests;
- crash-window tests;
- no broker.

### V41-PQ-001F5F — Paper Broker Certification Harness

Scope to be separately reviewed. Do not proceed directly to broker execution.

## Unit-of-work direction

Future conceptual shape:

```python
with execution_uow.transaction() as tx:
    aggregate = tx.aggregates.get(aggregate_id)
    reservation = tx.idempotency.reserve(...)
    tx.commands.record(...)
    tx.transitions.append(...)
    tx.aggregates.save(next_aggregate, expected_revision=...)
    tx.commit()
```

The unit of work owns transaction boundaries. Repositories own record-specific
access. Neither may know about Streamlit, scanners, supervisors, broker SDKs,
or UI.

## Implementation readiness

F5E1 is not authorized until ADR-007 receives review and the technology spike
scope is accepted or waived explicitly.

## Non-execution statement

No persistence, repository, database, migration, durable idempotency, broker
execution, runtime wiring, or Live behavior is implemented by this plan.
