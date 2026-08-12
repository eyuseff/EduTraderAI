# ADR-007: Execution Persistence and Idempotency

## 1. Title

Execution Persistence and Idempotency Foundation.

## 2. Status

Accepted.

## 3. Date

2026-08-05.

## 4. Context

F5B defines immutable Paper execution contracts. F5C defines advisory
eligibility. F5D1 defines the pure lifecycle state machine. F5D2 defines a
side-effect-free dry-run executor. None of these slices persist authoritative
execution state, reserve idempotency durably, recover after restart, or
coordinate multiple workers.

## 5. Problem

Broker execution must not begin until command identity, payload fingerprints,
idempotency, lifecycle revisions, broker references, receipts, failures,
transition history, and unknown outcomes can survive restarts and concurrent
workers safely.

## 6. Decision proposal

Introduce a dedicated execution persistence bounded context before any Paper
broker execution. The proposal is a transactional execution store with a
materialized aggregate table plus append-only transition journal, command
records, idempotency reservations, receipts, failures, broker-reference
records, approval references, and reconciliation records.

## 7. Persistence bounded context

Execution persistence owns only Paper execution state. It must not own broker
truth, UI state, scanner strategy state, portfolio persistence, qualification
state, validation evidence, or simulator state.

## 8. Aggregate ownership

The execution aggregate is the local source of truth for expected local
lifecycle state. The broker remains the source of truth for external broker
facts.

## 9. Durable command identity

One logical command ID maps to exactly one canonical command payload
fingerprint. Same command ID with a different payload is a command conflict.

## 10. Durable payload fingerprint

The canonical payload fingerprint must be persisted with the command record and
used for replay, conflict detection, audit, and reconciliation.

## 11. Durable idempotency key

One logical idempotency key must not create multiple broker operations. Same
key and same logical operation is replay. Same key and different logical
operation is conflict.

## 12. Execution revision ownership

`PaperExecutionRevision` belongs to execution lifecycle persistence only. It is
separate from qualification revisions, broker versions, and database row
versions.

## 13. Transaction boundaries

Local authoritative changes for one lifecycle transition must commit
atomically. No transaction may span an external broker network call.

## 14. Lifecycle snapshot

The aggregate snapshot stores current lifecycle state, current execution
revision, flags, quantities, broker reference if known, and last receipt,
failure, and transition references.

## 15. Append-only transition history

Accepted lifecycle transitions are appended once. History must not be silently
rewritten. Corrections occur through new reconciliation or compensating records.

## 16. Broker-reference persistence

Broker references are observations, not authority. They are persisted only
after normalized observation or dispatch result handling.

## 17. Receipt persistence

Receipts record normalized local or broker response facts. Repository save
success does not imply broker success.

## 18. Failure persistence

Failures record stable kind, severity, retryability, terminality,
reconciliation requirement, and safe message code.

## 19. Reconciliation facts

Reconciliation records preserve local revision, broker observations, result
classification, and resulting lifecycle transition. Unknown outcomes remain
unresolved after restart until reconciliation.

## 20. Approval persistence

Approval records store only safe references, approval fingerprints, binding
fingerprints, approval kind, approved-at, expiry, and future revocation facts if
supported.

## 21. Emergency-stop facts

Emergency-stop facts are guard evidence. They must be recorded as safe
structured facts and must not be inferred from stale runtime memory.

## 22. Restart recovery

Startup recovery must identify ambiguous states such as `DISPATCH_PENDING`,
`DISPATCHED`, `OUTCOME_UNKNOWN`, `RECONCILIATION_REQUIRED`, `CANCEL_PENDING`,
`REPLACE_PENDING`, and `PARTIALLY_FILLED`. It must not infer broker outcome from
local state alone.

## 23. Unknown-outcome recovery

Unknown outcomes remain unresolved until read-only broker evidence or operator
reconciliation resolves them. Blind resubmission is prohibited.

## 24. Cross-process coordination

Correctness must rely on database uniqueness constraints, transactions, row
locks or compare-and-swap updates, and durable idempotency. Process-local locks
alone are insufficient for broker execution.

## 25. Uniqueness constraints

Required uniqueness includes command ID, idempotency key plus logical
fingerprint, transition record identity, broker reference identity, receipt
fingerprint, and failure fingerprint.

## 26. Optimistic concurrency

Aggregate updates must use:

```sql
UPDATE execution_aggregates
SET ...
WHERE aggregate_id = ?
AND revision = ?
```

If zero rows are affected, no transition is appended, no side-effect intent is
activated, and no broker call may occur.

## 27. Security and redaction

Never persist API keys, secret keys, access tokens, refresh tokens, passwords,
authorization headers, cookies, private keys, raw SDK objects, raw HTTP payloads
without approved normalization, environment snapshots, or secret-bearing stack
traces.

## 28. Retention

Retention policy must be defined before durable execution. Active aggregates,
commands, idempotency records, lifecycle history, receipts, failures,
approvals, reconciliation records, broker references, and audit records have
different retention needs and require future legal/regulatory review.

## 29. Migration strategy

Persistence requires schema versioning, forward migrations, backup before
migration, migration checksums, startup compatibility checks, old-client
rejection, dry-run migration tests, and validation after migration.

## 30. Rollback strategy

Rollback may disable future persistence integration before broker execution,
restore a backup, or revert wiring. Rollback must not delete command history,
reset idempotency keys, rewrite revisions, remove broker references, erase
unknown outcomes, or silently reinitialize the database.

## 31. Storage-technology requirements

The storage layer must support transactions, uniqueness constraints, optimistic
concurrency, append-only history, crash recovery, backups, migrations,
deterministic tests, and cross-process safety for the supported deployment
mode.

## 32. Consequences

This ADR adds a design gate before broker execution. It increases engineering
scope but prevents duplicate broker submission, silent history loss, and
restart ambiguity.

## 33. Risks

Primary risks are duplicate broker submission, stale aggregate writes,
idempotency races, crash after broker acceptance, broker-reference uniqueness
conflicts, migration failure, audit gaps, and secret persistence.

## 34. Alternatives considered

- Keep execution state in memory.
- Use JSON/JSONL files as authoritative execution state.
- Reuse portfolio SQLite tables.
- Implement full event sourcing immediately.
- Require PostgreSQL immediately.

## 35. Rejected alternatives

In-memory state is not restart-safe. JSON files are insufficient for execution
authority under concurrency. Portfolio tables do not own execution facts. Full
event sourcing is more complex than currently justified. PostgreSQL may be
appropriate later but needs operational justification.

## 36. Deferred decisions

Final storage selection, schema details, outbox timing, encryption mechanism,
backup procedure, retention durations, and multi-host deployment support remain
deferred to review/spike and implementation slices.

## 37. Sentinel review requirements

Sentinel review is complete. F5E1A and F5E1B may begin only within the bounded scopes accepted by the review: persistence contracts, unit-of-work ports, deterministic in-memory reference behavior, and contract tests. Durable backend implementation remains blocked until the authorized comparative storage spike is completed and reviewed.

## 38. Non-execution statement

This ADR implements nothing. Persistence does not authorize execution.
Repository save success does not imply broker success. Idempotency reservation
does not imply dispatch. Broker references are observations, not authority.
Broker execution remains prohibited until separately authorized.

## 39. Sentinel ADR-007 review disposition

Project Sentinel reviewed ADR-007 and the supporting F5E0 persistence architecture documents on 2026-08-05.

Review result: APPROVED.

ADR-007 final status: Accepted.

Storage-technology position: `AUTHORIZE_COMPARATIVE_SPIKE`.

F5E1 readiness: `READY_WITH_CONDITIONS`.

F5E1A — Persistence Contracts and Unit-of-Work Ports: `READY_FOR_IMPLEMENTATION`.

F5E1B — Deterministic In-Memory Reference Adapter: `READY_FOR_IMPLEMENTATION`.

Broker-execution readiness: `NOT_AUTHORIZED`.

Acceptance basis:

- source-of-truth hierarchy is explicit;
- durable record inventory is complete at ADR level;
- command and idempotency replay/conflict rules are deterministic;
- aggregate revision compare-and-swap is explicit;
- transaction boundaries prohibit broker calls inside local transactions;
- ambiguous external-effect windows require unknown-outcome or reconciliation handling;
- append-only transition history is preserved;
- migration, rollback, backup/restore, security, and retention constraints are explicit;
- no unresolved critical or major findings remain.

This acceptance does not implement storage and does not authorize broker execution.

## 40. Authorized next slices

The next authorized implementation slice is `V41-PQ-001F5E1A — Persistence Contracts and Unit-of-Work Ports`.

`V41-PQ-001F5E1B — Deterministic In-Memory Reference Adapter` is also ready after or alongside F5E1A if it remains non-production and contract-test-only.

`V41-PQ-001F5E-SPIKE — SQLite/PostgreSQL Execution Durability Comparison` is authorized as an isolated, non-production spike. It must not call brokers, wire runtime, mutate production state, use real credentials, use `state/simulated_broker.json`, or select Live behavior.

No durable database adapter is authorized until spike results are reviewed.
