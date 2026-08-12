# Sentinel ADR-006 Transition Audit

## Summary

Initial transition count: 30.

Final transition count: 30.

Audit result: PASS.

Every proposed transition has a stable ID, source, input, guard, destination,
revision behavior, replay behavior, future evidence intent, failure destination,
and reconciliation classification. No transition authorizes broker dispatch by
itself.

## Transition audit table

| ID | Input category | Source clarity | Destination clarity | Revision behavior | Replay behavior | Safety disposition |
|---|---|---|---|---|---|---|
| PX-TRN-001 | Operator/application | PASS | PASS | Initializes aggregate revision | Same command replays | Accepted |
| PX-TRN-002 | Eligibility recording | PASS | PASS | +1 accepted | Replay original | Accepted; non-authoritative |
| PX-TRN-003 | Eligibility recording | PASS | PASS | +1 accepted | Replay original | Accepted; command-terminal |
| PX-TRN-004 | Eligibility recording | PASS | PASS | +1 accepted | Replay original | Accepted; indeterminate blocks dispatch |
| PX-TRN-005 | Operator/application | PASS | PASS | +1 accepted | Replay original | Accepted; approval remains non-authoritative |
| PX-TRN-006 | Persistence/idempotency | PASS | PASS | +1 accepted | Replay original | Accepted; future persistence required |
| PX-TRN-007 | Internal lifecycle | PASS | PASS | +1 accepted | Replay original | Accepted; ready is non-authoritative |
| PX-TRN-008 | Internal lifecycle | PASS | PASS | +1 accepted | No repeated intent | Accepted; future orchestrator only |
| PX-TRN-009 | Internal lifecycle | PASS | PASS | +1 accepted | No repeated dispatch | Accepted; ambiguity goes unknown |
| PX-TRN-010 | Broker observation | PASS | PASS | +1 accepted | Duplicate no-op | Accepted; acknowledgement is not fill |
| PX-TRN-011 | Broker observation | PASS | PASS | +1 accepted | Duplicate no-op | Accepted; broker rejection command-terminal |
| PX-TRN-012 | Internal lifecycle | PASS | PASS | +1 accepted | Replay original | Accepted; restricted non-terminal |
| PX-TRN-013 | Broker observation | PASS | PASS | +1 accepted | Duplicate no-op | Accepted; partial fill non-terminal |
| PX-TRN-014 | Broker observation | PASS | PASS | +1 accepted | Duplicate no-op | Accepted; fill aggregate-terminal |
| PX-TRN-015 | Broker observation | PASS | PASS | +1 only for new fact | Duplicate no-op | Accepted; monotonic only |
| PX-TRN-016 | Broker observation | PASS | PASS | +1 accepted | Duplicate no-op | Accepted |
| PX-TRN-017 | Operator/application | PASS | PASS | +1 accepted | Replay original | Accepted; request is not cancellation |
| PX-TRN-018 | Internal lifecycle | PASS | PASS | +1 accepted | No repeated cancel | Accepted |
| PX-TRN-019 | Broker observation | PASS | PASS | +1 accepted | Duplicate no-op | Accepted; cancellation does not reverse fills |
| PX-TRN-020 | Broker observation | PASS | PASS | +1 accepted | Duplicate no-op | Accepted; fill wins race |
| PX-TRN-021 | Operator/application | PASS | PASS | +1 accepted | Replay original | Accepted; native replace only |
| PX-TRN-022 | Internal lifecycle | PASS | PASS | +1 accepted | No repeated replace | Accepted |
| PX-TRN-023 | Broker observation | PASS | PASS | +1 accepted | Duplicate no-op | Accepted; replacement command-terminal |
| PX-TRN-024 | Broker observation | PASS | PASS | +1 accepted | Duplicate no-op | Accepted; fill wins race |
| PX-TRN-025 | Reconciliation | PASS | PASS | +1 accepted | Replay original | Accepted; no automatic retry |
| PX-TRN-026 | Reconciliation | PASS | Bounded by prior normal state | +1 accepted | Replay original | Accepted; concrete destination required |
| PX-TRN-027 | Reconciliation | PASS | Bounded by broker-truth state | +1 accepted | Replay original | Accepted; broker evidence required |
| PX-TRN-028 | Reconciliation | PASS | PASS | No-op unless new fact | Duplicate no-op | Accepted; remains restricted |
| PX-TRN-029 | Operator/application | PASS | PASS | +1 accepted | Replay original | Accepted; pre-dispatch only |
| PX-TRN-030 | Operator/application | PASS | PASS | +1 accepted | Replay original | Accepted; unrecoverable only |

## Invalid-transition audit

Invalid transitions fail closed:

- `CREATED` directly to `FILLED`.
- `ELIGIBILITY_EVALUATED` directly to `DISPATCHED`.
- `READY_FOR_DISPATCH` treated as broker authorization.
- `DISPATCH_PENDING` treated as `BROKER_ACKNOWLEDGED`.
- `BROKER_ACKNOWLEDGED` treated as `FILLED`.
- `FILLED` to `CANCELLED`.
- `CANCEL_REQUESTED` treated as `CANCELLED`.
- `REPLACE_REQUESTED` treated as `REPLACED`.
- `OUTCOME_UNKNOWN` to another `SUBMIT`.
- `RECONCILIATION_REQUIRED` overwritten without reconciliation.

## Final transition IDs

PX-TRN-001 through PX-TRN-030.
