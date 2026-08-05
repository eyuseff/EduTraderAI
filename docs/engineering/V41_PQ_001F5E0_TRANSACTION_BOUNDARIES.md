# V41-PQ-001F5E0 Transaction Boundaries

## Purpose

Define future atomic transaction boundaries for execution persistence. This is
design only; no repository, database, or migration is implemented.

## Governing rules

- All authoritative local state updates for one lifecycle transition commit
  atomically or not at all.
- No database transaction may span an external broker network call.
- A crash after possible broker acceptance must not cause blind resubmission.
- A `NullEventPublisher` or best-effort publisher is not part of the
  authoritative transaction.

## Command intake transaction

Inputs: immutable command, expected revision, idempotency key, initial aggregate
facts.
Locks/constraints: command ID uniqueness, idempotency uniqueness,
aggregate revision compare-and-swap.
Writes: command record, idempotency reservation, aggregate snapshot,
transition record, receipt/failure reference.
Failure behavior: rollback all local writes.
External-effect boundary: no broker contact.

## Exact replay transaction

Detect same command ID and same payload. Return original logical outcome.
Append no transition, increment no revision, activate no side-effect intent,
and perform no broker call.

## Command conflict transaction

Detect same command ID with different payload. Record a safe conflict failure,
preserve aggregate state, increment no revision, and perform no dispatch.

## Idempotency replay transaction

Detect different command ID using same idempotency key and same logical payload.
Return original logical outcome and suppress duplicate broker operation.

## Idempotency conflict transaction

Detect same idempotency key with different payload. Record conflict, perform no
mutation toward dispatch, and perform no broker call.

## Lifecycle transition transaction

Atomically:

1. lock or compare aggregate revision;
2. validate lifecycle transition;
3. append transition record;
4. update aggregate snapshot;
5. persist receipt, failure, and evidence references;
6. increment execution revision exactly once.

## Dispatch preparation transaction

Before future broker contact, atomically:

- confirm expected revision;
- confirm idempotency reservation;
- confirm approval reference;
- confirm guard facts;
- transition to `DISPATCH_PENDING`;
- persist dispatch intent;
- commit before external call.

## External-effect boundary

Safe future sequence:

1. Transaction A: reserve command/idempotency, validate revision, record
   `DISPATCH_PENDING`, persist dispatch intent, commit.
2. External call: broker adapter invocation outside the transaction.
3. Transaction B: record broker response, persist broker reference if known,
   transition to `DISPATCHED`, `BROKER_ACKNOWLEDGED`, `BROKER_REJECTED`,
   `OUTCOME_UNKNOWN`, or `RECONCILIATION_REQUIRED`, commit.

## Crash windows

| Crash window | Required behavior |
|---|---|
| Before Transaction A commit | No authoritative dispatch intent exists; caller may retry safely. |
| After Transaction A commit before broker call | Recovery sees `DISPATCH_PENDING`; no blind submit without claim proof. |
| During broker call | Mark or preserve ambiguity; require reconciliation before retry. |
| After broker acceptance before Transaction B | Must not blindly resubmit; read-only broker reconciliation required. |
| After Transaction B commit | Replay stored result. |
| Duplicate worker restart | Unique constraints and revision CAS select one winner. |

## Cancellation transaction

Cancellation must record request and pending state before external cancel. Fills
can race cancellation; broker observations must drive final truth.

## Replacement transaction

Replacement must preserve original aggregate identity, record replacement
request/pending state, and reject cancel-and-submit fallback unless separately
authorized.

## Reconciliation transaction

Reconciliation records local starting revision, normalized broker observations,
classification, operator-action need, and resulting lifecycle transition. It
must not rewrite earlier history.

## Failure atomicity

| Failure point | Required behavior |
|---|---|
| Command record succeeds but reservation fails | Roll back command record. |
| Reservation succeeds but aggregate save fails | Roll back reservation. |
| Aggregate save succeeds but journal append fails | Roll back aggregate save. |
| Journal append succeeds but receipt save fails | Roll back journal and aggregate. |
| Audit/evidence write fails | Do not treat external publisher as authoritative; require durable local outbox if needed. |
| Broker reference uniqueness fails | Roll back response transaction and require reconciliation. |
| Transaction commit fails | Treat as unknown locally until storage can prove result. |
| Process crashes mid-transaction | Database atomicity must leave either old state or committed new state, not partial authority. |

## Outbox assessment

Direct publish inside a transaction is unsafe because external publish cannot
roll back with the database. Publish after commit can lose events. Execution
audit should be local and durable first. A transactional outbox is recommended
before external event publication becomes required, but F5E0 does not implement
one.
