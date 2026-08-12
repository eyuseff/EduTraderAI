# V41-PQ-001F5E1A Implementation Report

## 1. Executive summary

V41-PQ-001F5E1A implements the pure application-layer persistence contracts
and unit-of-work ports accepted by ADR-007 and Sentinel ADR-007 review.

This slice defines durability vocabulary only. It stores nothing and executes
nothing.

## 2. Starting baseline

Starting HEAD: `51054871349e5d3ce4ec6398dc95ea67142f32aa`.

Baseline: 1,732 tests passing, 76 architecture tests passing, 85.7% coverage,
ADR-004/005/006/007 Accepted, F5D1 lifecycle core implemented, F5D2 dry-run
executor implemented, and broker execution `NOT_AUTHORIZED`.

Expected unrelated dirty file: `state/simulated_broker.json`.

## 3. Scope implemented

- Immutable persistence record contracts.
- Immutable repository result contracts.
- Command replay and conflict result contracts.
- Idempotency reservation result contracts.
- Optimistic-concurrency result contracts.
- Restart-discovery query and result contracts.
- Repository ports.
- Unit-of-work and command-intake session ports.
- Typed persistence errors.
- Deterministic serialization and fingerprints.
- Architecture fitness tests.
- Focused contract tests.

## 4. Scope excluded

No adapter, in-memory implementation, SQLite, PostgreSQL, Redis, JSON storage,
filesystem storage, migration, durable idempotency, durable lifecycle state,
broker port, broker adapter, broker call, runtime wiring, simulator access,
event publication, metrics, logging, UI, API, CLI, dependency, environment
switch, configuration, or Live behavior was implemented.

## 5. ADR-007 conformance

F5E1A follows ADR-007 by separating contracts from infrastructure. The package
defines storage-neutral records and ports beneath the execution application
layer without choosing a backend.

## 6. Package structure

Implemented package:

- `volcanoes/application/execution/persistence/__init__.py`
- `volcanoes/application/execution/persistence/enums.py`
- `volcanoes/application/execution/persistence/errors.py`
- `volcanoes/application/execution/persistence/contracts.py`
- `volcanoes/application/execution/persistence/ports.py`
- `volcanoes/application/execution/persistence/unit_of_work.py`

## 7. Public exports

The execution package now explicitly exports persistence records, results,
conflicts, repository ports, unit-of-work ports, enums, errors, and
`canonical_payload_text`.

## 8. Durable record contracts

Implemented ADR-007 record contracts:

- `ExecutionAggregateRecord`
- `ExecutionCommandRecord`
- `ExecutionIdempotencyRecord`
- `ExecutionTransitionRecord`
- `ExecutionBrokerReferenceRecord`
- `ExecutionReceiptRecord`
- `ExecutionFailureRecord`
- `ExecutionApprovalRecord`
- `ExecutionReconciliationRecord`

All are frozen dataclasses with slots and explicit schema versions.

## 9. Aggregate record

`ExecutionAggregateRecord` represents the durable materialized local lifecycle
view. It preserves `PaperExecutionRevision` as the authoritative local CAS
revision and excludes qualification revision and broker version.

## 10. Command record

`ExecutionCommandRecord` binds one command ID to one canonical command payload
fingerprint, canonical command JSON text, approval fingerprint, policy
fingerprint, operation, expected execution revision, and processing outcome.

## 11. Idempotency record

`ExecutionIdempotencyRecord` binds one idempotency key to one logical-operation
fingerprint and a reservation status. It represents reserved, completed,
conflicted, and reconciliation-required states without implementing leases or
expiry.

## 12. Transition record

`ExecutionTransitionRecord` represents accepted append-only lifecycle
transitions only. It requires `previous_revision + 1 == next_revision` and
rejects replay indicators other than `NONE`.

## 13. Broker-reference record

`ExecutionBrokerReferenceRecord` stores normalized broker references,
adapter-safe identity, status, timestamps, active flag, and replacement
reference. It contains no raw broker object, credentials, or payload.

## 14. Receipt record

`ExecutionReceiptRecord` wraps the existing normalized `PaperExecutionReceipt`
in a durable record fingerprint and explicit recorded timestamp.

## 15. Failure record

`ExecutionFailureRecord` wraps the existing normalized `PaperExecutionFailure`
in a durable record fingerprint and explicit recorded timestamp.

## 16. Approval record

`ExecutionApprovalRecord` stores approval fingerprint, bound fingerprint,
approval kind, safe approver reference, approval timestamps, optional expiry,
and optional revocation reference.

## 17. Reconciliation record

`ExecutionReconciliationRecord` stores reconciliation identity, starting local
revision/state, broker observation references, result classification, optional
resulting transition/revision, operator-action flag, unresolved flag, and safe
reason code.

## 18. Result contracts

Implemented immutable results:

- `RecordLoadResult`
- `AggregateSaveResult`
- `CommandRegistrationResult`
- `IdempotencyReservationResult`
- `TransitionAppendResult`
- `ReplayLookupResult`
- `RestartDiscoveryResult`
- `UnitOfWorkCommitResult`

Expected conflicts are represented as result data, not exceptions.

## 19. Conflict contracts

`ExecutionPersistenceConflict` records conflict kind, severity, safe code,
safe message, optional aggregate/command/idempotency identities, expected
revision, actual revision, schema version, and deterministic conflict
fingerprint.

## 20. Repository ports

Implemented Protocol ports:

- `ExecutionAggregateRepository`
- `ExecutionCommandRepository`
- `ExecutionIdempotencyRepository`
- `ExecutionTransitionJournal`
- `ExecutionBrokerReferenceRepository`
- `ExecutionReceiptRepository`
- `ExecutionFailureRepository`
- `ExecutionApprovalRepository`
- `ExecutionReconciliationRepository`
- `ExecutionRestartDiscoveryRepository`

The ports accept immutable records and return immutable result contracts.

## 21. Unit-of-work port

`ExecutionUnitOfWork` exposes repository attributes plus explicit `commit()`
and `rollback()`. Context-manager methods are declarative and do not define
hidden auto-commit behavior.

`ExecutionPersistenceSession` provides a narrow atomic command-intake surface
without embedding lifecycle rules.

## 22. Command intake transaction boundary

The session contract exposes `register_command`, `reserve_idempotency`,
`load_aggregate`, `append_transition`, `save_aggregate`, `record_receipt`, and
`record_failure`. Implementations must make those operations atomic later, but
this slice implements no transaction behavior.

## 23. Replay contracts

`ReplayLookupResult`, `CommandRegistrationResult`, and
`IdempotencyReservationResult` distinguish exact command replay, logical
idempotency replay, command conflict, and idempotency conflict.

## 24. Optimistic-concurrency contract

`ExecutionAggregateRepository.save` and `ExecutionPersistenceSession.save_aggregate`
require explicit `expected_revision: PaperExecutionRevision` and return
`AggregateSaveResult` rather than exposing row counts or backend details.

## 25. Restart-discovery contracts

`ExecutionRestartDiscoveryQuery` locates consequential non-terminal aggregate
states by immutable state filters, optional timestamp window, limit, cursor,
and Paper mode. `RestartDiscoveryResult` returns immutable aggregate records,
cursor, completion flag, and deterministic result fingerprint.

No recovery, broker query, or runtime action is performed.

## 26. Timestamp model

All record timestamps are caller supplied and timezone-aware. The contracts do
not call `datetime.now`, `time.time`, database defaults, or hidden clocks.

## 27. Canonicalization/fingerprints

The package reuses existing execution canonicalization and SHA-256 fingerprint
helpers. Public prefixes include:

- `par` aggregate record
- `pcm` command record
- `plo` logical operation
- `pir` idempotency record
- `ptr` transition record
- `pbf` broker-reference record
- `prr` receipt record
- `pfr` failure record
- `pav` approval record
- `prn` reconciliation record
- `pco` persistence conflict
- `puw` unit-of-work result

## 28. Error model

Implemented typed structural errors:

- `ExecutionPersistenceError`
- `ExecutionPersistenceContractError`
- `ExecutionPersistenceInvariantError`
- `ExecutionPersistenceTransactionError`

Expected conflicts are immutable result data, not exceptions.

## 29. Immutability

Public records, results, conflicts, and queries are frozen dataclasses with
slots. Public collections are tuples. Contracts expose deterministic equality
and deterministic primitive serialization.

## 30. Security/redaction

Contracts reject sensitive terms in safe text fields and exclude credentials,
raw broker objects, raw HTTP payloads, database handles, ORM objects, SQL
expressions, mutable mappings, raw exceptions, stack traces, environment
snapshots, and private account details.

## 31. Architecture boundaries

Architecture tests now verify the persistence package does not import adapters,
brokers, simulators, scanners, supervisors, runtime orchestration, readiness,
qualification runtime integration, database clients, filesystem helpers, event
publishers, logging, metrics, HTTP clients, environment configuration,
randomness, clocks, threads, or processes.

They also verify no concrete repository adapter, database schema, migration,
broker port, or runtime call site was introduced.

## 32. Tests

Focused tests added:

- `tests/test_execution_persistence_records.py`
- `tests/test_execution_persistence_results.py`
- `tests/test_execution_persistence_ports.py`
- `tests/test_execution_persistence_unit_of_work.py`
- `tests/test_execution_persistence_restart_discovery.py`
- `tests/test_execution_persistence_determinism.py`

Architecture tests were extended in `tests/test_architecture_dependencies.py`.

## 33. Verification

Focused persistence tests: 111 passed.

Architecture tests: 81 passed.

Full verification is recorded in the final task report.

## 34. Known limitations

- No implementation stores records.
- No implementation replays records after restart.
- No backend has been selected.
- No durable idempotency exists.
- No durable lifecycle state exists.
- No reconciliation service exists.

## 35. Deferred capabilities

- F5E1B deterministic in-memory reference adapter.
- F5E-SPIKE SQLite/PostgreSQL comparison.
- Durable backend adapter.
- Migration tooling.
- Backup/restore verification.
- Broker-effect persistence.
- Reconciliation service.
- Transactional outbox.

## 36. Risks

Primary remaining risks are future backend selection, transaction atomicity,
cross-process races, unknown-outcome recovery, migration safety, and
operator-facing reconciliation. These remain unimplemented by design.

## 37. Next recommended slice

`V41-PQ-001F5E1B — Deterministic In-Memory Reference Adapter`.

The comparative SQLite/PostgreSQL spike remains authorized and may follow
F5E1B.

## 38. Explicit non-persistence statement

F5E1A implements contracts and ports only. It implements no adapter, no
in-memory repository, no database, no schema, no migration, no durable storage,
no durable idempotency, and no durable lifecycle state.

## 39. Explicit non-execution statement

F5E1A implements no broker port, broker adapter, broker call, runtime wiring,
execution authority, runtime action, simulator access, simulator mutation,
scanner or supervisor lifecycle change, event publisher, metrics, logging, UI,
API, CLI, dependency, environment switch, configuration file, Live behavior, or
credential use.

Broker execution remains `NOT_AUTHORIZED`. V41-PQ-001 remains in progress.
