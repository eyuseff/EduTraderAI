# Sentinel ADR-007 Idempotency Audit

## Audit result

PASS.

ADR-007 defines deterministic replay and conflict rules sufficiently for acceptance and F5E1 contract design.

## Reservation timing decision

Authoritative reservation occurs during command intake, before `IDEMPOTENCY_RESERVED`, before `READY_FOR_DISPATCH`, and before any future dispatch preparation can reach a broker-call boundary.

The reservation binds one idempotency key permanently to one logical-operation fingerprint. The command record binds one command ID permanently to one canonical payload fingerprint.

## Replay and conflict matrix

| Scenario | Result | Mutation | Revision increment | Broker call |
|---|---|---:|---:|---:|
| Same command ID + same payload | Exact replay of original logical result | No | No | No |
| Same command ID + different payload | Command conflict | No | No | No |
| Different command ID + same idempotency key + same logical fingerprint | Logical replay of original result or pending state | No | No | No |
| Same idempotency key + different logical fingerprint | Idempotency conflict | No | No | No |
| Concurrent identical requests | One reservation wins; others replay/observe pending | Winner only | Winner only if accepted transition | Winner only later if separately authorized |
| Concurrent conflicting requests | At most one reservation wins; conflicts fail closed | Winner only | Winner only if accepted transition | No losing broker call |
| Stuck reservation after crash | Recovery, lease/status handling, or operator/reconciliation path | Controlled recovery only | No unsafe increment | No blind call |

## Deterministic replay requirements

A future implementation must persist:

- command ID;
- canonical command payload fingerprint;
- idempotency key;
- logical-operation fingerprint;
- operation;
- aggregate ID;
- correlation ID;
- expected execution revision;
- result reference or pending/recovery status;
- serialization version.

Replay must never reconstruct behavior from mutable process memory, dry-run output, JSONL audit, or simulator state.

## Conflict behavior

Conflicts are fail-closed and revision-neutral. Conflict responses may produce safe evidence later, but evidence does not become authority and cannot unlock a broker call.

## Stuck reservation behavior

A reservation may be pending after restart only if its status indicates no safe completed result. Recovery must use explicit status or lease semantics. A stuck key must not be deleted and reused while broker-effect ambiguity is possible.

## Required F5E1 contract tests

F5E1A/B should define contract tests for:

- exact command replay;
- command conflict;
- idempotency replay;
- idempotency conflict;
- concurrent identical reservation;
- concurrent conflicting reservation;
- pending reservation recovery representation;
- revision-neutral replay/conflict;
- no broker dependency;
- no simulator dependency.
