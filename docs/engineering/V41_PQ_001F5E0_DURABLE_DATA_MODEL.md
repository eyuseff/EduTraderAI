# V41-PQ-001F5E0 Durable Data Model

## Purpose

Define the minimum durable records required before Paper broker execution can
be implemented. This document is design only; no schema is implemented.

## Current fact

Execution commands, eligibility results, lifecycle aggregates, and dry-run
results are currently immutable in memory only. Portfolio persistence already
uses SQLite, audit automation can write JSONL, qualification harnesses use
in-memory fake repositories, and the simulator has unrelated JSON runtime
state. None of these are acceptable authoritative execution stores.

## Record summary

| Record | Owner | Mutability | Restart use |
|---|---|---|---|
| Execution aggregate | Execution persistence | Materialized current view | Resume local lifecycle |
| Execution command | Execution persistence | Immutable after insert | Replay/conflict detection |
| Idempotency reservation | Execution persistence | State changes by transaction | Suppress duplicate broker operation |
| Lifecycle transition | Execution journal | Append-only | Reconstruct and audit state |
| Broker reference | Execution persistence | Append/update status only | Broker reconciliation |
| Receipt | Execution persistence | Immutable | Recover normalized results |
| Failure | Execution persistence | Immutable | Explain failed/rejected work |
| Approval | Execution persistence | Immutable plus future revocation | Prove approval binding |
| Reconciliation | Execution persistence | Append-only | Resolve local/broker gaps |

## Execution aggregate

Fields:

- aggregate ID;
- correlation ID;
- current lifecycle state;
- current execution revision;
- Paper mode;
- requested quantity;
- cumulative fill quantity;
- active broker reference;
- outcome-unknown flag;
- reconciliation-required flag;
- command terminality;
- aggregate terminality;
- last transition ID;
- last receipt fingerprint;
- last failure fingerprint;
- created timestamp;
- updated timestamp;
- serialization version.

Primary key: aggregate ID.
Indexes: lifecycle state, reconciliation-required flag, outcome-unknown flag,
active broker reference.
Mutable fields: current materialized state only.
Transaction participation: every accepted transition update.
Retention: until closed and archival policy permits compaction.

## Execution command record

Fields:

- command ID;
- aggregate ID;
- correlation ID;
- idempotency key;
- operation;
- expected revision;
- canonical payload fingerprint;
- canonical command representation;
- approval fingerprint;
- policy fingerprint;
- received timestamp;
- processing outcome;
- serialization version.

Primary key: command ID.
Unique constraints: command ID to payload fingerprint; idempotency key to
logical payload fingerprint.
Mutable fields: processing outcome only.
Restart use: exact replay and command conflict detection.

## Idempotency reservation

Fields:

- idempotency key;
- logical operation fingerprint;
- command ID;
- aggregate ID;
- reservation state;
- original result reference;
- created timestamp;
- resolved timestamp;
- conflict status;
- serialization version.

Primary key: idempotency key.
Unique constraints: idempotency key plus logical operation fingerprint.
Mutable fields: reservation state, result reference, resolved timestamp,
conflict status.
Restart use: duplicate broker operation suppression.

## Lifecycle transition record

Fields:

- transition record ID;
- aggregate ID;
- transition ID;
- source state;
- destination state;
- previous revision;
- next revision;
- input identity;
- command ID;
- broker observation ID;
- replay indicator;
- evidence fingerprint;
- side-effect intent kinds;
- safe reason code;
- timestamp supplied by caller or infrastructure;
- serialization version.

Primary key: transition record ID.
Unique constraints: aggregate ID plus next revision; command/broker
observation replay identity where applicable.
Mutable fields: none.
Restart use: audit, reconstruction, consistency verification.

## Broker reference record

Fields:

- normalized broker reference;
- aggregate ID;
- command ID;
- broker adapter identity;
- Paper environment;
- lifecycle relationship;
- first-seen timestamp;
- last-seen timestamp;
- active/replaced/terminal status;
- serialization version.

Primary key: normalized broker reference plus broker adapter identity.
Unique constraints: one active broker reference per aggregate unless replacement
history records the transition.
Mutable fields: status and last-seen timestamp.
Restart use: read-only broker reconciliation.

## Receipt record

Fields:

- receipt fingerprint;
- command ID;
- aggregate ID;
- normalized kind;
- normalized status;
- broker reference;
- observed revision;
- outcome-known flag;
- reconciliation-required flag;
- safe message code;
- serialization version.

Primary key: receipt fingerprint.
Mutable fields: none.
Restart use: replay original logical outcome.

## Failure record

Fields:

- failure fingerprint;
- command ID;
- aggregate ID;
- stable failure kind;
- severity;
- terminality;
- retryability;
- reconciliation requirement;
- operator-action requirement;
- safe message code;
- serialization version.

Primary key: failure fingerprint.
Mutable fields: none.
Restart use: explain safe failures and preserve conflict history.

## Approval record

Fields:

- approval fingerprint;
- bound command or intent fingerprint;
- approval kind;
- approver safe reference;
- approved-at timestamp;
- expires-at timestamp;
- revocation fact if later supported;
- serialization version.

Primary key: approval fingerprint.
Mutable fields: revocation fact only if separately modeled.
Restart use: prove approval existed before dispatch preparation.

## Reconciliation record

Fields:

- reconciliation request identity;
- aggregate ID;
- starting local revision;
- broker observation references;
- result classification;
- resulting lifecycle transition;
- operator-action requirement;
- created timestamp;
- resolved timestamp;
- serialization version.

Primary key: reconciliation request identity.
Mutable fields: resolved timestamp/result only inside reconciliation transaction.
Restart use: prevent blind resubmission after ambiguity.

## Source-of-truth hierarchy

1. Immutable command truth: command record and payload fingerprint.
2. Local lifecycle truth: aggregate snapshot plus transition journal.
3. Broker observation truth: normalized broker observations and references.
4. Reconciliation-derived truth: reconciliation records and resulting
   lifecycle transitions.
5. Audit history: append-only supporting evidence, not operational authority.
6. Materialized current view: derived convenience, not a replacement for
   history.

Dry-run results, simulator state, validation evidence, and audit JSONL do not
become execution state.

## Sentinel ADR-007 review update

Review result: PASS. The durable record inventory is accepted at ADR level: execution aggregate, command, idempotency reservation, transition journal entry, broker-reference record, receipt, failure, approval, and reconciliation record. Existing portfolio SQLite tables, JSONL audit files, dry-run output, qualification in-memory repositories, and simulator JSON state remain non-authoritative.
