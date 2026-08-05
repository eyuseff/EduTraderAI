# V41-PQ-001F5E0 Persistence Architecture Review

## 1. Executive summary

Review decision: ACCEPTED WITH CONDITIONS.

F5E0 defines the durability architecture required before broker execution:
transactional command intake, durable idempotency, optimistic execution
revision, append-only lifecycle history, restart recovery, broker-reference
persistence, reconciliation prerequisites, security/redaction, migration, and
rollback. It implements no persistence.

## 2. Starting baseline

Starting HEAD: `4df00534acca09732c432811701f0be2b9d72647`.

Baseline: 1,732 tests, 76 architecture tests, 85.7% coverage, ADR-004/005/006
Accepted, F5B/F5C/F5D1/F5D2 implemented, and no durable execution persistence.

## 3. Scope reviewed

Execution persistence, idempotency, transaction boundaries, restart recovery,
cross-process coordination, storage technology, migration, rollback, security,
retention, repository ports, unit of work, and risk sequencing.

## 4. Scope excluded

No repository, database, schema, migration, broker port, broker adapter,
runtime wiring, event publisher, metrics, logging, simulator access, or Live
behavior.

## 5. Current-state inventory

- Execution contracts/lifecycle/dry-run are immutable and in-memory only.
- Dry-run results are not persisted.
- Portfolio has SQLite persistence unrelated to execution authority.
- Audit automation can write JSONL and is not operational execution state.
- Validation manifests preserve evidence integrity and are not execution state.
- Simulator JSON is unrelated mutable runtime state and not an execution store.
- Qualification harnesses use deterministic in-memory fake repositories.
- Operational events default to `NullEventPublisher`.
- Current source of truth for execution is the immutable in-process object graph.

## 6. Current durability gaps

No restart-safe command store, durable idempotency, execution aggregate store,
transition journal, broker-reference store, receipt/failure store,
reconciliation store, migration path, backup/restore, or cross-process
execution authority exists.

## 7. Proposed persistence architecture

Use an execution bounded context with transactional unit of work, materialized
aggregate table, append-only transition journal, command table, idempotency
reservations, receipt/failure tables, broker-reference records, approval
records, and reconciliation records.

## 8. Source-of-truth model

Local lifecycle truth is the durable execution aggregate plus journal. Broker
truth is external broker observation. Reconciliation resolves differences
without rewriting history.

## 9. Durable data model

See `V41_PQ_001F5E0_DURABLE_DATA_MODEL.md`.

## 10. Aggregate record

Stores aggregate ID, correlation ID, lifecycle state, revision, Paper mode,
quantities, flags, terminality, broker reference, last transition, receipt, and
failure fingerprints.

## 11. Command record

Stores command ID, aggregate ID, correlation ID, idempotency key, operation,
expected revision, canonical payload fingerprint, canonical representation,
approval and policy fingerprints, received timestamp, and processing outcome.

## 12. Idempotency record

Stores idempotency key, logical operation fingerprint, command ID, aggregate
ID, reservation state, original result reference, timestamps, and conflict
status.

## 13. Transition journal

Append-only accepted lifecycle transition history with source/destination
state, previous/next revision, transition ID, command/observation identity,
side-effect intent kinds, evidence fingerprint, and safe reason code.

## 14. Broker-reference record

Stores normalized broker reference, adapter identity, Paper environment,
aggregate and command relationship, first/last seen timestamps, and active or
terminal status.

## 15. Receipt record

Stores normalized receipt fingerprint, command, aggregate, kind, status, broker
reference, observed revision, outcome-known flag, reconciliation flag, and safe
message code.

## 16. Failure record

Stores failure fingerprint, kind, severity, terminality, retryability,
reconciliation requirement, operator-action requirement, and safe message code.

## 17. Approval record

Stores approval fingerprint, bound fingerprint, approval kind, safe approver
reference, approved-at, expires-at, and future revocation fact if supported.

## 18. Reconciliation record

Stores reconciliation identity, aggregate, starting revision, broker
observation references, classification, resulting transition, and
operator-action requirement.

## 19. Transaction boundaries

See `V41_PQ_001F5E0_TRANSACTION_BOUNDARIES.md`.

## 20. External-effect boundary

Future broker calls must occur between two local transactions: commit
`DISPATCH_PENDING` before the call, then persist normalized result afterward.
No transaction spans the broker network call.

## 21. Idempotency model

See `V41_PQ_001F5E0_IDEMPOTENCY_AND_REPLAY_MODEL.md`.

## 22. Optimistic-concurrency model

See `V41_PQ_001F5E0_OPTIMISTIC_CONCURRENCY_MODEL.md`.

## 23. Cross-process model

Use uniqueness constraints, row locks or compare-and-swap, durable claims, and
transactional idempotency. Process-local locks alone are insufficient for
broker execution.

## 24. Restart and recovery

See `V41_PQ_001F5E0_RESTART_AND_RECOVERY_MODEL.md`.

## 25. Append-only history

Decision: state table plus append-only transition journal. This is not full
event sourcing. Full event sourcing is deferred because current needs are met
with a simpler materialized aggregate plus immutable journal.

## 26. Materialized aggregate

The materialized aggregate is a current-state view derived from accepted
transitions. It cannot replace the append-only journal.

## 27. Repository-port design

Prefer a small unit-of-work surface coordinating aggregate, command,
idempotency, journal, receipt, failure, and reconciliation repositories. Ports
must live inward of adapters and know nothing about brokers or UI.

## 28. Unit-of-work design

One execution unit of work should own transaction boundaries and commit/rollback
semantics for command intake and lifecycle transitions.

## 29. Storage-technology assessment

See `V41_PQ_001F5E0_STORAGE_TECHNOLOGY_ASSESSMENT.md`.

## 30. Technology decision

Decision: REQUIRE_TECHNOLOGY_SPIKE.

SQLite is promising for initial single-machine Paper execution under strict
conditions, but a bounded spike must prove concurrency, rollback, WAL,
backup/restore, migration, and crash-window behavior before selection.

## 31. Migration model

See `V41_PQ_001F5E0_MIGRATION_AND_ROLLBACK_PLAN.md`.

## 32. Rollback model

Rollback must preserve command history, idempotency records, revisions, broker
references, unknown outcomes, and transition history.

## 33. Backup and restore

Backup/restore must verify aggregate/journal consistency, uniqueness,
fingerprints, schema version, and secret exclusion.

## 34. Security and redaction

See `V41_PQ_001F5E0_SECURITY_RETENTION_AND_REDACTION.md`.

## 35. Retention

Retention is deferred pending legal/regulatory review. Execution authority
records must not be deleted while needed for idempotency, audit, or
reconciliation.

## 36. Outbox assessment

A transactional outbox is recommended before external event publication becomes
authoritative. Direct publish inside transactions and best-effort publish after
commit are unsafe for authoritative evidence.

## 37. Testing strategy

Future tests must cover repository contracts, exact replay after restart,
command/idempotency conflicts, stale revisions, concurrent races, duplicate and
conflicting broker observations, crash windows, transaction rollback, journal
consistency, migrations, backup/restore, secret exclusion, corruption handling,
cross-process workers, and no broker interaction.

## 38. Deployment constraints

Until a storage technology is selected and proven, broker execution remains
prohibited. SQLite, if later selected, is limited to single-machine deployment
with WAL, foreign keys, backups, explicit migrations, and no network filesystem.

## 39. Risks

| ID | Risk | Severity | Prevention | Detection | Target slice |
|---|---|---|---|---|---|
| F5E-R01 | Duplicate broker submission | Critical | Durable idempotency and dispatch boundary | Replay/concurrency tests | F5E2/F5E3 |
| F5E-R02 | Stale aggregate write | High | Revision CAS | Stale conflict tests | F5E1 |
| F5E-R03 | Partial transaction commit | Critical | Unit of work transaction | rollback tests | F5E2 |
| F5E-R04 | Lost transition history | High | Append-only journal | snapshot/journal audit | F5E2 |
| F5E-R05 | Idempotency race | Critical | unique constraints | multi-worker tests | F5E3 |
| F5E-R06 | Payload fingerprint mismatch | High | command uniqueness | conflict tests | F5E1 |
| F5E-R07 | Database corruption | High | backups/checks | restore drills | F5E2 |
| F5E-R08 | SQLite locking misuse | High | deployment constraints | spike tests | F5E-SPIKE |
| F5E-R09 | Crash after broker acceptance | Critical | unknown outcome/reconcile | crash-window tests | F5E3 |
| F5E-R10 | Broker reference conflict | High | unique reference records | reconciliation tests | F5E2 |
| F5E-R11 | Migration failure | High | backup/checksum | migration tests | F5E2 |
| F5E-R12 | Secret persistence | Critical | redaction contract | secret scanners | F5E2 |
| F5E-R13 | Audit gap | Medium | durable local evidence/outbox | consistency checks | F5E2 |
| F5E-R14 | Legacy/new dual execution | Critical | feature-gate and idempotency | integration tests | F5F |
| F5E-R15 | Simulator contamination | High | explicit boundary tests | path/token checks | F5E1 |

## 40. Accepted decisions

- Persistence bounded context is separate from broker truth.
- Materialized aggregate plus append-only journal is preferred over full event
  sourcing for now.
- Idempotency must be durable before broker execution.
- No transaction may span a broker call.
- Process-local locks are insufficient for broker execution.

## 41. Conditional decisions

SQLite may be acceptable only after the technology spike proves required
properties under single-machine constraints.

## 42. Deferred decisions

Final database, encryption mechanism, outbox implementation timing, retention
durations, backup tooling, and multi-host support.

## 43. Rejected alternatives

In-memory authoritative execution, JSON/JSONL authoritative execution, reuse of
simulator JSON, reuse of audit JSONL, silent broker-state overwrite, and direct
broker execution without durable idempotency.

## 44. ADR-007 readiness

ADR-007 is ready for Sentinel review as Proposed.

## 45. Implementation readiness

F5E1 is blocked pending Sentinel ADR-007 review or explicit approval of the
bounded storage technology spike.

## 46. Recommended implementation sequence

F5E-SPIKE, F5E1, F5E2, F5E3, then F5F certification harness.

## 47. Next recommended slice

SENTINEL ADR-007 REVIEW.

## 48. Explicit non-execution statement

No persistence was implemented. No database was selected for implementation.
No repository was implemented. No durable idempotency was implemented. No
broker was called. No runtime wiring was added. No simulator state was
accessed. No execution authority was added. No Live behavior was added.
V41-PQ-001 remains incomplete.
