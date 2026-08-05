# Sentinel ADR-007 Data Model Audit

## Audit result

PASS.

The durable data model is complete enough to accept ADR-007 and guide F5E1A/F5E1B contracts. It is not a schema and does not authorize a database adapter.

## Source-of-truth hierarchy

| Rank | Source | Authority |
|---:|---|---|
| 1 | Immutable execution command record | What was requested. |
| 2 | Execution aggregate snapshot | Current expected local lifecycle state. |
| 3 | Append-only transition journal | Accepted local state-transition history. |
| 4 | Normalized broker observations | Received external broker facts. |
| 5 | Reconciliation record | Resolution of local/broker disagreement. |
| 6 | Audit/evidence material | Supporting evidence only. |
| 7 | Dry-run results | Simulation only. |
| 8 | Simulator JSON state | Unrelated runtime state; never authoritative. |

## Record audit

| Record | Ownership | Canonical identity / primary key | Unique constraints | Mutable fields | Immutable fields | Append-only status | Revision behavior | Restart role | Indexes | Conflict behavior | Migration behavior |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Execution aggregate | Execution persistence | Aggregate ID | Aggregate ID; active broker reference relationship checked separately | Current state, revision, flags, last references, updated timestamp | Aggregate identity, mode, correlation root, creation metadata | Materialized current view, not append-only | Accepted transition increments once by CAS | Resume local lifecycle and discover recovery work | state, revision, recovery flags, broker reference | Stale CAS fails closed | Versioned rows; snapshot/journal consistency validated |
| Execution command | Execution persistence | Command ID | Command ID to payload fingerprint; idempotency key to logical fingerprint through reservation | Processing outcome only | Canonical payload fingerprint, command identity, operation, expected revision | Insert-once with bounded outcome update | Replay/conflict neutral | Reconstruct request and replay result | command ID, idempotency key, aggregate ID, correlation ID | Different payload is command conflict | Canonical serialization versioned |
| Idempotency reservation | Execution persistence | Idempotency key | Key plus logical-operation fingerprint | Reservation state, original result reference, resolved timestamp | Original logical fingerprint and first command relationship | Not append-only but never deleted/reused while replay possible | Replay/conflict neutral | Suppress duplicate broker operation | key, fingerprint, state, aggregate ID | Different fingerprint is idempotency conflict | Lease/status semantics versioned |
| Lifecycle transition journal entry | Execution journal | Transition record ID | Aggregate ID plus next revision; replay identities where applicable | None | source/destination, previous/next revision, input identity, evidence fingerprint | Append-only | Accepted transition increments once | Reconstruct and audit state | aggregate ID, next revision, state, command/observation ID | Duplicate exact transition replays/no-ops; conflict reconciles | Immutable history preserved across migrations |
| Broker-reference record | Execution persistence | Normalized broker reference plus adapter identity | One active claim per aggregate/reference relationship | Status, last-seen timestamp | Normalized reference, adapter identity, first-seen relationship | Status update allowed; history via journal | Observation handling may transition aggregate | Read-only reconciliation and duplicate suppression | broker reference, aggregate ID, active status | Two active claims require reconciliation | Normalization rules versioned |
| Receipt record | Execution persistence | Receipt fingerprint | Receipt fingerprint | None | normalized kind/status/reference/outcome flags | Append-only immutable receipt | Receipt may support transition; does not prove broker success alone | Replay normalized result | command ID, aggregate ID, broker reference | Duplicate receipt suppressed by fingerprint | Serialization versioned |
| Failure record | Execution persistence | Failure fingerprint | Failure fingerprint | None | kind, severity, retryability, terminality, safe code | Append-only immutable failure | May support terminal/reconciliation transition | Explain safe failure after restart | command ID, aggregate ID, severity | Duplicate failure suppressed | Safe-code taxonomy versioned |
| Approval record | Execution persistence | Approval fingerprint | Approval fingerprint and binding fingerprint | Revocation fact only if separately modeled | approval kind, safe approver reference, binding, time window | Append-only facts plus optional revocation fact | Approval recording is local transition input | Prove approval existed before dispatch | binding fingerprint, expiry | Missing/expired approval rejects | Retention and redaction versioned |
| Reconciliation record | Execution persistence | Reconciliation request identity | reconciliation identity; related aggregate/revision | Resolved timestamp/result only in reconciliation transaction | starting revision, broker observations, classification | Append-only resolution record | Reconciliation transition increments once if accepted | Resolve unknown/conflicting outcome | aggregate ID, state, unresolved flag | Conflicting reconciliation fails closed | History preserved; no revision reset |

## Missing or unjustified records

No additional record is required before F5E1A/F5E1B. Emergency-stop facts remain guard evidence and should be represented through safe structured fields or evidence references when the relevant external guard exists; they do not require a separate ADR-level record in this slice.

No listed record is unjustified: each prevents a distinct duplicate, replay, restart, reconciliation, or audit-safety failure.

## Non-authoritative stores

The following repository mechanisms must not become execution authority:

- Existing portfolio SQLite snapshots.
- Existing generic `orders` or `trades` tables.
- JSON/JSONL audit files.
- Validation evidence manifests.
- Qualification in-memory repositories.
- Dry-run results.
- `state/simulated_broker.json`.
