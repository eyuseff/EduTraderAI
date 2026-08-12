# V41-PQ-001F5E0 Idempotency and Replay Model

## Purpose

Define durable idempotency and replay semantics before broker execution. This
is design only.

## Reservation point

Recommendation: reserve idempotency during command intake after command shape
validation and before any transition that could lead toward dispatch. This is
the safest point because it prevents duplicate workers from advancing the same
logical operation differently before dispatch preparation.

Idempotency reservation does not imply dispatch.

## Same command ID and same payload

Classify as exact replay:

- return original logical outcome;
- append no new transition;
- increment no revision;
- emit no duplicate side-effect intent;
- perform no broker call.

## Same command ID and different payload

Classify as command conflict:

- record safe conflict;
- preserve aggregate state;
- increment no revision;
- perform no dispatch.

## Different command ID, same idempotency key, same logical payload

Classify as idempotency replay:

- return original logical outcome;
- suppress duplicate broker operation;
- append no new dispatch transition;
- keep original broker-reference relationship.

## Same idempotency key and different payload

Classify as idempotency conflict:

- record safe conflict;
- preserve aggregate state;
- increment no revision;
- perform no dispatch.

## Same aggregate, same expected revision, competing commands

Exactly one command may win the aggregate compare-and-swap transaction. Other
commands fail stale revision or conflict. No losing command may activate a
broker side effect.

## Duplicate broker observation

Same broker observation identity and same fingerprint is replay:

- no duplicate state mutation;
- no revision increment;
- return original observation result.

## Conflicting broker observation

Same broker observation identity with different facts, or incompatible broker
facts for the same aggregate, must:

- record conflict;
- require reconciliation;
- avoid silent overwrite;
- perform no corrective broker action automatically.

## Durable records required

- Command record for command ID and payload fingerprint.
- Idempotency reservation for key and logical operation fingerprint.
- Transition journal for accepted transition identities.
- Receipt/failure records for replayed logical results.
- Broker observation identity for observation replay/conflict.

## Replay after restart

Restarted workers must resolve replay from durable records only. In-memory
process state is advisory at best and is insufficient for broker execution.

## Sentinel ADR-007 review update

Review result: PASS. Reservation timing is fixed at command intake / before `IDEMPOTENCY_RESERVED`, before `READY_FOR_DISPATCH`, and before any future broker-call boundary. Replay and conflict decisions are deterministic and revision-neutral. No duplicate broker call may follow replay or conflict.
