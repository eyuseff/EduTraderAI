# V41-PQ-001F5D0 Concurrency and Replay Model

## Purpose

Define proposed concurrency, replay, duplicate, and idempotency rules before
implementation. This is design only.

Sentinel review status: accepted as part of ADR-006 acceptance on 2026-08-04.

## Replay and duplicate matrix

| Case | Expected behavior | Mutation | Revision | Side-effect intent |
|---|---|---:|---:|---:|
| Same command ID + same payload | Deterministic replay of original logical outcome | No | No increment | No repeat |
| Same command ID + different payload | Hard duplicate conflict; audit-required failure | No | No increment | None |
| Different command ID + same idempotency key + same logical payload | Logical idempotency replay | No new mutation | No increment | No repeat |
| Same idempotency key + materially different payload | Idempotency conflict | No | No increment | None |
| Duplicate broker observation | Observational replay | No unless new fact | No increment for duplicate | None |
| Conflicting broker observation | Reconciliation required | No overwrite | No normal increment | None |

## Required future durable records

To enforce these rules across restarts or processes, future persistence must
retain:

- command ID to payload fingerprint;
- idempotency key to logical operation fingerprint;
- aggregate ID to current state and execution revision;
- accepted transition history;
- side-effect-intent history;
- dispatch boundary evidence;
- broker reference history;
- receipt fingerprints;
- failure fingerprints;
- reconciliation records.

## Concurrency scenarios

| Scenario | Proposed fail-safe behavior |
|---|---|
| Two simultaneous `SUBMIT` commands | One aggregate revision may advance; the other must stale-fail or idempotency-replay. |
| `SUBMIT` and `CANCEL` race | Cancel cannot apply before broker reference or accepted working state. |
| Broker fill and `CANCEL` race | Fill truth wins if broker proves fill; cancellation cannot reverse fills. |
| Broker fill and `REPLACE` race | Fill truth wins if broker proves fill before replacement. |
| Emergency stop and dispatch race | If dispatch may have occurred, enter unknown/reconciliation rather than pretending dispatch did not happen. |
| Duplicate command delivery | Replay original outcome when payload is identical. |
| Out-of-order broker observations | Accept only monotonic truthful facts; otherwise require reconciliation. |
| Persistence revision conflict | Reject before side-effect intent. |
| Reconciliation during active command | Restrict state-changing commands until reconciliation completes. |
| Legacy and new executor both attempting submission | Prohibited; one execution authority at a time. |

## Stale revision rule

Expected execution revision must match current aggregate revision for
state-changing commands. Stale inputs fail before any future side-effect intent.

## Unknown outcome concurrency rule

While in `OUTCOME_UNKNOWN` or `RECONCILIATION_REQUIRED`, only future read/query,
reconcile, operator-abort where safe, and emergency-stop visibility updates may
be accepted. New submit, cancel, or replace commands are blocked unless a later
ADR defines a narrowly safe exception.

## Process boundary

In-memory enforcement is insufficient for broker side effects. Durable
coordination is required before controlled Paper broker submission.
