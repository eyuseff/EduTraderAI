# V41-PQ-001F5D0 Execution State Model

## Purpose

Define the proposed Paper execution lifecycle state model before implementing a
lifecycle core or dry-run executor. This is design only.

## Current implementation fact

No production execution lifecycle state machine exists. F5B provides inert
`PaperExecutionStatus` values, receipts, failures, and execution revisions.
F5C provides advisory eligibility results. No executor, broker port, broker
adapter, persistence, runtime wiring, reconciliation, or Live behavior exists.

## Accepted initial lifecycle states

| State | Required | Truth owner | Terminal | Recoverable | Persistence before broker use | Initial dry-run use | Notes |
|---|---:|---|---:|---:|---:|---:|---|
| `CREATED` | Yes | Lifecycle core | No | Yes | Yes | Yes | Local aggregate exists; no eligibility recorded. |
| `ELIGIBILITY_EVALUATED` | Yes | Lifecycle core | No | Yes | Yes | Yes | Eligibility result recorded; no dispatch authority. |
| `INELIGIBLE` | Yes | Lifecycle core | Command-terminal | Yes | Yes | Yes | Terminal for that command, not necessarily aggregate. |
| `APPROVAL_CONFIRMED` | Yes | Approval boundary + lifecycle core | No | Yes | Yes | Yes | Approval evidence recorded; not dispatch. |
| `IDEMPOTENCY_RESERVED` | Yes | Persistence/idempotency layer | No | Yes | Yes | Deferred | Requires durable reservation before broker use. |
| `READY_FOR_DISPATCH` | Yes | Lifecycle core | No | Yes | Yes | Dry-run as `WOULD_DISPATCH` only | Local pre-dispatch state; no broker fact. |
| `DISPATCH_PENDING` | Yes | Future orchestrator | No | Yes | Yes | Deferred | Side-effect intent prepared but not crossed. |
| `DISPATCHED` | Yes | Future orchestrator evidence | No | Yes | Yes | No broker truth in dry-run | Request may have crossed broker boundary. |
| `BROKER_ACKNOWLEDGED` | Yes | Broker adapter observation | No | Yes | Yes | No | Broker reference accepted; not fill. |
| `PARTIALLY_FILLED` | Yes | Broker adapter observation | No | Yes | Yes | No | Cumulative fill below ordered quantity. |
| `FILLED` | Yes | Broker adapter observation | Aggregate-terminal | No | Yes | No | Full fill confirmed. |
| `CANCEL_REQUESTED` | Yes | Operator/application command | No | Yes | Yes | Dry-run as intent only | Local cancel request accepted; not broker cancellation. |
| `CANCEL_PENDING` | Yes | Future orchestrator evidence | No | Yes | Yes | No | Cancel request may have crossed boundary. |
| `CANCELLED` | Yes | Broker adapter observation | Broker-order terminal | No | Yes | No | Remaining quantity cancelled; fills remain true. |
| `REPLACE_REQUESTED` | Yes | Operator/application command | No | Yes | Yes | Dry-run as intent only | Native replace requested; not replacement. |
| `REPLACE_PENDING` | Yes | Future orchestrator evidence | No | Yes | Yes | No | Replace request may have crossed boundary. |
| `REPLACED` | Yes | Broker adapter observation | Command-terminal | Yes | Yes | No | Terminal for replace command; aggregate may continue. |
| `BROKER_REJECTED` | Yes | Broker adapter observation | Command-terminal | No | Yes | No | Broker rejected a dispatched command. |
| `OUTCOME_UNKNOWN` | Yes | Lifecycle core | No | Yes | Yes | No | Ambiguous post-dispatch state; reconciliation mandatory. |
| `RECONCILIATION_REQUIRED` | Yes | Reconciliation service | No | Yes | Yes | No | State-changing commands restricted. |
| `FAILED_TERMINAL` | Yes | Lifecycle core/operator | Terminal | No | Yes | Dry-run as terminal failure only | Unrecoverable local failure. |
| `ABORTED_BEFORE_DISPATCH` | Yes | Lifecycle core/operator | Command-terminal | No | Yes | Yes | Safe local abort before broker boundary. |

## Rejected candidate states

| Candidate | Disposition | Reason |
|---|---|---|
| `ELIGIBLE` | Rejected as lifecycle state | Eligibility is an observation/result, not stable aggregate state. Use `ELIGIBILITY_EVALUATED` plus recorded decision. |
| `RECOVERED` | Rejected as steady state | Recovery is a transition outcome into a concrete lifecycle state, not a durable state. |
| `WORKING` | Deferred | Existing F5B has this status, but initial model can use `BROKER_ACKNOWLEDGED` plus broker observations until adapter mapping is designed. |
| `DRY_RUN_ACCEPTED` | Rejected as lifecycle state | Dry-run belongs to a separate future dry-run outcome model, not broker lifecycle state. |
| `DRY_RUN_REJECTED` | Rejected as lifecycle state | Same reason; use dry-run result/failure facts. |

## Deferred states

`WORKING`, adapter-specific open statuses, routed venue states, and broker
native replace sub-states are deferred to broker certification and controlled
Paper broker submission.

## Terminality model

Command-terminal states: `INELIGIBLE`, `ABORTED_BEFORE_DISPATCH`,
`BROKER_REJECTED`, `REPLACED`, `FAILED_TERMINAL`.

Broker-order terminal states: `FILLED`, `CANCELLED`, `BROKER_REJECTED`.

Aggregate-terminal states: `FILLED`, `FAILED_TERMINAL`, and `CANCELLED` when no
remaining working broker reference exists.

Non-terminal restricted states: `OUTCOME_UNKNOWN` and
`RECONCILIATION_REQUIRED`.

## Ownership rule

The lifecycle core owns accepted local state. Broker adapters can only propose
state changes through normalized observations. Future persistence must preserve
state, revision, command fingerprint, idempotency key, receipts, failures, and
reconciliation markers before any broker side effect is enabled.
