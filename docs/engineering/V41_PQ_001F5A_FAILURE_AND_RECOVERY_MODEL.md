# V41-PQ-001F5A Failure and Recovery Model

## Purpose

Define future Paper execution failures and recovery rules without implementing
retry, reconciliation, persistence, or broker calls.

## Failure taxonomy

| Failure | Retryable | Terminal | Reconciliation | Operator action | Authority impact | Safe to expose | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| Contract validation failure | No | Yes | No | No | Yes | Yes | Reject before dispatch. |
| Eligibility failure | No | Yes | No | Sometimes | Yes | Yes | Includes unsupported source/mode. |
| Approval failure | No | Yes | No | Yes | Yes | Yes | Readiness cannot satisfy approval. |
| Emergency-stop failure | No | Yes | No | Yes | Yes | Yes | New execution fails closed. |
| Paper-mode violation | No | Yes | No | Yes | Yes | Yes | Critical safety failure. |
| Live-mode violation | No | Yes | No | Yes | Yes | Yes | Live structurally unsupported. |
| Stale revision | No | Yes before dispatch | No | Maybe | Yes | Yes | Caller must refresh. |
| Duplicate conflict | No | Yes | Maybe | Maybe | Yes | Yes | Same key different payload. |
| Unsupported market capability | No | Yes | No | Maybe | Yes | Yes | Unknown capability fails closed. |
| Unsupported order type | No | Yes | No | Maybe | Yes | Yes | Local rejection. |
| Invalid quantity | No | Yes | No | No | Yes | Yes | Local rejection. |
| Invalid price | No | Yes | No | No | Yes | Yes | Local rejection. |
| Invalid time in force | No | Yes | No | Maybe | Yes | Yes | Capability failure. |
| Market closed | Maybe later | Yes for command | No | Maybe | Yes | Yes | Submit should not wait silently. |
| Broker unavailable before dispatch | Bounded | Yes for command | No | Maybe | No | Yes | No external side effect. |
| Transport timeout before dispatch | Bounded | Yes for command | No | No | No | Yes | Only if proven pre-dispatch. |
| Transport timeout after possible dispatch | No blind retry | No | Yes | Maybe | Yes | Yes | `OUTCOME_UNKNOWN`. |
| Authentication failure | No | Yes | No | Yes | Yes | Yes, redacted | Adapter/config issue. |
| Authorization failure | No | Yes | No | Yes | Yes | Yes, redacted | Account permission issue. |
| Rate limit | Bounded read retry | No | Maybe | Maybe | No | Yes | Avoid retry storms. |
| Broker rejection | No | Yes | No | Maybe | Yes | Yes | Safe broker reason only. |
| Broker validation failure | No | Yes | No | Maybe | Yes | Yes | May reveal capability gap. |
| Duplicate broker request | No | Maybe | Yes | Yes | Yes | Yes | Reconcile local/broker identity. |
| Acknowledgement ambiguity | No | No | Yes | Maybe | Yes | Yes | Do not classify as success/failure. |
| Outcome unknown | No | No | Yes | Maybe | Yes | Yes | Blocks state-changing commands. |
| Partial fill | Not failure by itself | No | Maybe | Maybe | Yes | Yes | Must model remaining quantity. |
| Cancellation race | No blind retry | No | Yes | Maybe | Yes | Yes | Fill truth wins. |
| Replacement race | No blind retry | No | Yes | Maybe | Yes | Yes | Native replace only initially. |
| Reconciliation mismatch | No | No | Yes | Yes | Yes | Yes | Block further action. |
| Persistence failure before dispatch | Maybe | Yes | No | Yes | Yes | Yes | Do not dispatch. |
| Persistence failure after dispatch | No | No | Yes | Yes | Yes | Yes | Audit gap risk. |
| Event publication failure | No | Maybe | No | Maybe | Maybe | Yes | Do not duplicate broker call. |
| Audit failure before dispatch | No | Yes | No | Yes | Yes | Yes | Fail closed. |
| Audit failure after dispatch | No | No | Yes | Yes | Yes | Yes | Broker truth needed. |
| Internal invariant violation | No | Yes | Maybe | Yes | Yes | Yes | Halt executor. |

Raw broker exceptions are not domain failures. Adapters must translate them into
typed, redacted failures.

## Retry policy

### Submit

- If failure is proven before dispatch, a caller may create a new command after
  refreshing state.
- If dispatch may have occurred, do not resubmit.
- Mark `OUTCOME_UNKNOWN` and reconcile.
- Reuse the same command identity and payload only to replay the same logical
  outcome, never to create a second broker order.

### Cancel

- Repeated cancel can be deterministic success or no-op only when the broker
  adapter proves that already-cancelled semantics are safe.
- Filled-before-cancel is a valid outcome and is not a cancellation failure.
- Unknown cancellation outcome requires reconciliation.

### Replace

- Do not assume atomicity unless broker-native replace semantics prove it.
- Initial design disables cancel-and-submit fallback.
- Replacement rejection is independent from original order state.
- Unknown replacement outcome requires reconciliation of both old and new
  broker references.

### Query

- Bounded retry is acceptable because query is read-only.
- Query failures must not mutate execution state except by adding safe
  observation/audit facts in a future implementation.

### Reconcile

- Bounded and observable.
- Must not submit, cancel, or replace orders.
- Failure to reconcile leaves the execution unresolved and may require operator
  action.

## Timeout policy

| Timeout | Meaning | Required behavior |
|---|---|---|
| Connection timeout before write | request likely not dispatched | local failure may be retryable if proven. |
| Request timeout during write | dispatch ambiguous | `OUTCOME_UNKNOWN`. |
| Acknowledgement timeout | broker may have accepted | `OUTCOME_UNKNOWN`. |
| Broker-status timeout | status unavailable | query failure or reconciliation required. |
| Reconciliation timeout | broker truth unavailable | unresolved; operator action may be required. |

Central rule: timeout after potential broker acceptance is neither success nor
failure. It is `OUTCOME_UNKNOWN`.

## Recovery model

Recovery sequence:

1. load durable local command and receipt history;
2. verify command fingerprints and idempotency reservations;
3. query broker by broker reference and safe client id where supported;
4. compare local state with broker order status, fills, cancellation state,
   replacement state, and identifiers;
5. produce a reconciliation result;
6. apply only an allowed revisioned transition;
7. record redacted audit evidence.

Recovery must never replay a state-changing command merely because local state
is incomplete.

## Cancellation and rollback

Cancellation is a broker request to stop remaining unfilled quantity. It cannot
undo fills and is not transactional rollback.

Rollback is local-only and pre-dispatch-only:

- release uncommitted reservation;
- revert pre-dispatch local transition;
- invalidate command before dispatch.

After dispatch, use reconciliation and compensating actions.

## Emergency-stop behavior

Initial model:

- global new-order stop;
- strategy/account/symbol stops as future extensions;
- cancel-only mode deferred;
- reconciliation-only mode allowed;
- open orders not automatically cancelled without separate authorization;
- fail closed when stop state is unknown;
- audit every stop activation and command blocked by stop.

Emergency stop does not depend on qualification readiness.
