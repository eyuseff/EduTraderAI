# ADR-011: F6B Durable Reconciliation History

Status: Proposed for F6B durability slice

## Decision

F6B reconciliation history reuses the existing append-only `ExecutionReconciliationRecord` and SQLite `execution_reconciliations` repository rather than creating a second persistence authority.

Each read-first reconciliation comparison derives a deterministic evidence fingerprint from all local facts, broker facts, conflict flags, evidence completeness, bounded reconciliation outcome, proposed lifecycle state, reason code, and operator-action flag. The reconciliation identity is derived from aggregate identity, starting execution revision, and that evidence fingerprint.

The durable record stores the evidence fingerprint alongside normalized broker references. The existing SQLite repository therefore provides the intended semantics: the same identity and same immutable record is exact replay; the same identity with different content is a reconciliation conflict; the table remains append-only under existing no-update/no-delete triggers.

This slice does not commit a lifecycle transition, query a broker, retry an order, dispatch an order, or select a recovery transition. A later F6B recovery slice must load durable local state and broker evidence first, compare them, record this immutable history, and only then propose any separately authorized lifecycle transition.

## Safety boundaries

- No broker I/O.
- No simulator access.
- No runtime wiring.
- No credentials.
- No automatic retry or redispatch.
- No Live behavior.
- No access to repository `state/`.
- No mutation is hidden inside the reconciliation model.

## Follow-on validation

The next slice must exercise the existing SQLite reconciliation repository under independent connections, exact replay, identity/content conflict, rollback, lock contention, append-only trigger violation, malformed/corrupted rows, and recovery restart scenarios before F6B may be considered durability-complete.
