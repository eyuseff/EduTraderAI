# V41-PQ-001F5D0 Transition Table

## Purpose

Define proposed Paper execution lifecycle transitions for future implementation.
This document is design only and introduces no production code.

Sentinel review status: accepted as part of ADR-006 acceptance on 2026-08-04.
Final transition count remains 30.

## Revision invariant

Each accepted lifecycle transition increments the execution aggregate revision
exactly once. Rejected transitions, stale commands, duplicate replays,
duplicate broker observations, and observational no-ops do not increment
revision.

## Proposed transition table

| ID | Source | Input | Guards | Destination | Revision | Future side-effect intent | Future evidence intent | Replay | Failure destination | Reconciliation | Terminality |
|---|---|---|---|---|---|---|---|---|---|---|---|
| PX-TRN-001 | none | CREATE_AGGREGATE | Valid Paper command envelope | `CREATED` | +1 from none to 0 | None | aggregate-created | same command replays | `FAILED_TERMINAL` | No | Non-terminal |
| PX-TRN-002 | `CREATED` | RECORD_ELIGIBILITY | F5C result present | `ELIGIBILITY_EVALUATED` | +1 | None | eligibility-recorded | replay original | `FAILED_TERMINAL` | No | Non-terminal |
| PX-TRN-003 | `ELIGIBILITY_EVALUATED` | RECORD_INELIGIBLE | decision `INELIGIBLE` | `INELIGIBLE` | +1 | None | ineligible-recorded | replay original | none | No | Command-terminal |
| PX-TRN-004 | `ELIGIBILITY_EVALUATED` | RECORD_INDETERMINATE | decision `INDETERMINATE` | `INELIGIBLE` | +1 | None | indeterminate-blocked | replay original | none | No | Command-terminal |
| PX-TRN-005 | `ELIGIBILITY_EVALUATED` | RECORD_APPROVAL | decision `ELIGIBLE`; approval bound and current | `APPROVAL_CONFIRMED` | +1 | None | approval-recorded | replay original | `INELIGIBLE` | No | Non-terminal |
| PX-TRN-006 | `APPROVAL_CONFIRMED` | RESERVE_IDEMPOTENCY | reservation succeeds | `IDEMPOTENCY_RESERVED` | +1 | reserve in future persistence | reservation-recorded | replay original | `FAILED_TERMINAL` | No | Non-terminal |
| PX-TRN-007 | `IDEMPOTENCY_RESERVED` | PREPARE_DISPATCH | expected revision matches; no emergency stop | `READY_FOR_DISPATCH` | +1 | none yet | ready-for-dispatch | replay original | `FAILED_TERMINAL` | No | Non-terminal |
| PX-TRN-008 | `READY_FOR_DISPATCH` | BEGIN_DISPATCH | authorized future orchestrator only | `DISPATCH_PENDING` | +1 | dispatch-intent future | pre-dispatch-evidence | no repeated intent | `ABORTED_BEFORE_DISPATCH` | No | Non-terminal |
| PX-TRN-009 | `DISPATCH_PENDING` | RECORD_DISPATCH | broker request may have crossed boundary | `DISPATCHED` | +1 | broker request already attempted by outer layer | dispatch-recorded | no repeated dispatch | `OUTCOME_UNKNOWN` | If ambiguous | Non-terminal |
| PX-TRN-010 | `DISPATCHED` | OBSERVE_BROKER_ACKNOWLEDGEMENT | trusted broker reference present | `BROKER_ACKNOWLEDGED` | +1 | None | broker-acknowledged | duplicate observation no-op | `RECONCILIATION_REQUIRED` | On conflict | Non-terminal |
| PX-TRN-011 | `DISPATCHED` | OBSERVE_BROKER_REJECTION | trusted rejection present | `BROKER_REJECTED` | +1 | None | broker-rejected | duplicate no-op | `RECONCILIATION_REQUIRED` | On conflict | Command-terminal |
| PX-TRN-012 | `DISPATCHED` | MARK_OUTCOME_UNKNOWN | possible dispatch, missing trusted outcome | `OUTCOME_UNKNOWN` | +1 | None | outcome-unknown | replay original | none | Yes | Restricted non-terminal |
| PX-TRN-013 | `BROKER_ACKNOWLEDGED` | OBSERVE_PARTIAL_FILL | cumulative filled < ordered quantity | `PARTIALLY_FILLED` | +1 | None | partial-fill-observed | duplicate no-op | `RECONCILIATION_REQUIRED` | On conflict | Non-terminal |
| PX-TRN-014 | `BROKER_ACKNOWLEDGED` | OBSERVE_FILL | cumulative filled == ordered quantity | `FILLED` | +1 | None | fill-observed | duplicate no-op | `RECONCILIATION_REQUIRED` | On conflict | Aggregate-terminal |
| PX-TRN-015 | `PARTIALLY_FILLED` | OBSERVE_PARTIAL_FILL | monotonic cumulative fill | `PARTIALLY_FILLED` | +1 when new fact | None | partial-fill-updated | duplicate no-op | `RECONCILIATION_REQUIRED` | On conflict | Non-terminal |
| PX-TRN-016 | `PARTIALLY_FILLED` | OBSERVE_FILL | cumulative filled == ordered quantity | `FILLED` | +1 | None | fill-observed | duplicate no-op | `RECONCILIATION_REQUIRED` | On conflict | Aggregate-terminal |
| PX-TRN-017 | `BROKER_ACKNOWLEDGED`/`PARTIALLY_FILLED` | REQUEST_CANCELLATION | expected revision matches; not filled | `CANCEL_REQUESTED` | +1 | None | cancel-requested | replay original | `FAILED_TERMINAL` | No | Non-terminal |
| PX-TRN-018 | `CANCEL_REQUESTED` | RECORD_CANCELLATION_DISPATCH | future cancel request may cross boundary | `CANCEL_PENDING` | +1 | cancel-intent future | cancel-dispatch-recorded | no repeated cancel | `OUTCOME_UNKNOWN` | If ambiguous | Non-terminal |
| PX-TRN-019 | `CANCEL_PENDING` | OBSERVE_CANCELLATION | broker confirms cancellation | `CANCELLED` | +1 | None | cancellation-confirmed | duplicate no-op | `RECONCILIATION_REQUIRED` | On conflict | Broker-order terminal |
| PX-TRN-020 | `CANCEL_PENDING` | OBSERVE_FILL | fill wins race | `FILLED` | +1 | None | fill-after-cancel-observed | duplicate no-op | `RECONCILIATION_REQUIRED` | On conflict | Aggregate-terminal |
| PX-TRN-021 | `BROKER_ACKNOWLEDGED`/`PARTIALLY_FILLED` | REQUEST_REPLACEMENT | native replace supported; expected revision matches | `REPLACE_REQUESTED` | +1 | None | replace-requested | replay original | `FAILED_TERMINAL` | No | Non-terminal |
| PX-TRN-022 | `REPLACE_REQUESTED` | RECORD_REPLACEMENT_DISPATCH | future replace request may cross boundary | `REPLACE_PENDING` | +1 | replace-intent future | replace-dispatch-recorded | no repeated replace | `OUTCOME_UNKNOWN` | If ambiguous | Non-terminal |
| PX-TRN-023 | `REPLACE_PENDING` | OBSERVE_REPLACEMENT | broker confirms native replace | `REPLACED` | +1 | None | replacement-confirmed | duplicate no-op | `RECONCILIATION_REQUIRED` | On conflict | Command-terminal |
| PX-TRN-024 | `REPLACE_PENDING` | OBSERVE_FILL | original filled before replace | `FILLED` | +1 | None | fill-before-replace-confirmed | duplicate no-op | `RECONCILIATION_REQUIRED` | On conflict | Aggregate-terminal |
| PX-TRN-025 | `OUTCOME_UNKNOWN` | REQUIRE_RECONCILIATION | unresolved ambiguity | `RECONCILIATION_REQUIRED` | +1 | read-only reconcile future | reconciliation-required | replay original | none | Yes | Restricted non-terminal |
| PX-TRN-026 | `RECONCILIATION_REQUIRED` | RECORD_RECONCILIATION_CONSISTENT | broker/local facts consistent | prior normal state | +1 | None | reconciliation-consistent | replay original | `FAILED_TERMINAL` | No | Depends destination |
| PX-TRN-027 | `RECONCILIATION_REQUIRED` | RECORD_RECONCILIATION_BROKER_AHEAD | broker has newer truthful state | matching broker state | +1 | None | broker-ahead-recovered | replay original | `FAILED_TERMINAL` | No | Depends destination |
| PX-TRN-028 | `RECONCILIATION_REQUIRED` | RECORD_RECONCILIATION_CONFLICTING | conflict remains | `RECONCILIATION_REQUIRED` | no-op unless new fact | None | conflict-recorded | no-op duplicate | `FAILED_TERMINAL` | Yes | Restricted non-terminal |
| PX-TRN-029 | `CREATED`/`ELIGIBILITY_EVALUATED`/`APPROVAL_CONFIRMED`/`IDEMPOTENCY_RESERVED`/`READY_FOR_DISPATCH` | ABORT_BEFORE_DISPATCH | no possible broker boundary crossing | `ABORTED_BEFORE_DISPATCH` | +1 | None | pre-dispatch-abort | replay original | none | No | Command-terminal |
| PX-TRN-030 | any non-terminal | FAIL_TERMINALLY | unrecoverable invariant/security/operator decision | `FAILED_TERMINAL` | +1 | None | terminal-failure | replay original | none | No | Terminal |

## Invalid transition examples

- `CREATED` directly to `FILLED`.
- `ELIGIBILITY_EVALUATED` directly to `DISPATCHED`.
- `ELIGIBLE` result treated as `READY_FOR_DISPATCH` without approval and
  idempotency reservation.
- `BROKER_ACKNOWLEDGED` treated as `FILLED`.
- `PARTIALLY_FILLED` treated as terminal.
- `FILLED` to `CANCELLED`.
- `CANCEL_REQUESTED` treated as `CANCELLED`.
- `REPLACE_REQUESTED` treated as `REPLACED`.
- `OUTCOME_UNKNOWN` to another `SUBMIT`.
- `RECONCILIATION_REQUIRED` overwritten by a broker observation without
  reconciliation.

## State coverage

Every accepted state has at least one incoming transition. Terminal states have
no state-changing outgoing transitions except reconciliation correction where
explicitly proposed in a future implementation.
