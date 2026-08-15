# ADR-010: F6B Paper Reconciliation Foundation

Status: Proposed for F6B foundation

## Decision

F6B begins with a pure, deterministic, read-only comparison layer. The layer accepts already-observed local and broker facts, classifies their relationship, and returns a bounded recovery proposal. It performs no broker query, persistence mutation, dispatch, retry, runtime wiring, simulator access, or Live behavior.

The accepted ADR-006 reconciliation outcomes remain the only public classifications: `CONSISTENT`, `LOCAL_AHEAD`, `BROKER_AHEAD`, `MISSING_LOCALLY`, `MISSING_AT_BROKER`, `CONFLICTING`, `UNRESOLVED`, and `OPERATOR_ACTION_REQUIRED`.

Permitted recovery destinations remain bounded to `BROKER_ACKNOWLEDGED`, `PARTIALLY_FILLED`, `FILLED`, `CANCELLED`, `BROKER_REJECTED`, `FAILED_TERMINAL`, or continued `RECONCILIATION_REQUIRED`.

Incomplete, contradictory, ownership-conflicting, reference-conflicting, or fill-conflicting evidence fails closed. It never authorizes automatic redispatch. Missing orders are not invented. `OUTCOME_UNKNOWN` remains unresolved until broker evidence proves a bounded destination.

## Scope of this foundation slice

- immutable reconciliation fact and decision contracts;
- deterministic local-versus-broker comparison;
- bounded recovery proposal validation;
- tests for missing-order gaps, outcome unknown, broker-reference conflicts, fill conflicts, incomplete evidence, and exact consistency.

## Explicitly deferred

- broker read adapters;
- SQLite reconciliation-history schema and repositories;
- crash/fault-injection durability matrices;
- adversarial multi-process concurrency tests;
- operator recovery command persistence;
- runtime composition;
- automatic retries or redispatch;
- broker credentials, Paper simulator access, and Live execution.

Those deferred items require separate validated slices before F6B can be considered complete.
