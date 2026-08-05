# V41-PQ-001F5E2A Implementation Plan

## Scope

This is the follow-on implementation sequence proposed by the F5E2A design. It is not implemented in this slice.

## Recommended next slice

`SENTINEL ADR-008 REVIEW`

ADR-008 should be reviewed before code implementation begins.

## After Sentinel approval

### V41-PQ-001F5E2B — SQLite Schema and Migration Foundation

- Create isolated infrastructure package.
- Add schema SQL.
- Add migration metadata model.
- Add migration runner.
- Add startup schema validation.
- Add migration tests.
- No repositories.
- No runtime wiring.
- No broker.

### V41-PQ-001F5E2C — Transactional SQLite Repository Adapter

- Implement F5E1A repository ports.
- Implement SQLite unit of work.
- Enforce command replay/conflict.
- Enforce idempotency replay/conflict.
- Enforce aggregate CAS.
- Enforce append-only transition journal.
- Persist broker-reference/receipt/failure/approval/reconciliation records.
- No runtime wiring.
- No broker.

### V41-PQ-001F5E2D — SQLite Durability, Recovery, Backup, and Concurrency Validation

- Restart tests.
- Corruption tests.
- Backup/restore tests.
- Lock-contention tests.
- Migration tests.
- Integrity checks.
- No broker.

### Later slice

`V41-PQ-001F5E1C — Transactional Execution Application Service`

Only after durable adapter validation and separate authorization.

## Implementation blockers

- ADR-008 must be reviewed.
- Database path/configuration mechanism must be approved.
- Backup/restore validation must be specified before runtime use.
- Broker execution remains separately unauthorized.
