# ADR-0003: Deterministic Manual Paper-Order Submission

- Status: Accepted
- Date: 2026-07-20

## Context

The Paper Order page already previews trades with the deterministic Volcanoes
`TradePlanner`, but confirmed orders have continued through the legacy
`PaperExecutionEngine`. That split creates a risk that the quantity or approval
shown to a user is not the quantity or approval used for submission.

The active root paper-broker interface is also an infrastructure API. Its
bracket-order types must not leak into the Volcanoes domain or application
services.

## Decision

Manual preview and manual submission share the same planner composition and
policy-parity configuration. `SubmitTradeService` receives canonical immutable
inputs, replans once, rejects an unapproved plan without broker access, and
delegates an approved immutable `TradePlan` to `ExecutionPipeline.submit_plan`.
The pipeline remains the sole domain-order construction and broker-execution
coordinator; sizing, risk, and policy calculations remain solely in
`TradePlanner`.

### Drift prevention

Submission uses fresh recomputation because the current root brokers expose no
reliable snapshot version. Immediately after confirmation, the outer adapter
copies a fresh account, positions, and open-order snapshot. The service compares
the resulting material plan fields with the immutable values displayed by the
preview: approval, quantity, dollar risk, position value, reasons, and risk
code. Any difference is reported as `PLAN_DRIFT`, and no broker order is sent.
The order is therefore submitted only when the freshly recomputed plan equals
the displayed plan.

The service also prevents a reused immutable command from being submitted twice
within one service instance. At the Streamlit boundary, a second confirmation is
additionally stopped by the fresh open-order snapshot and duplicate-order
policy.

### Broker boundary

`PaperBrokerExecutionAdapter` is an outward adapter. It implements the existing
Volcanoes `Broker` port and translates an already-sized domain order into the
root broker's bracket-order call. It may translate values and broker response
metadata, but it must not recalculate quantity, risk, exposure, approval, stop,
or target values. Concrete broker imports remain outside `volcanoes`.

The dependency direction is:

```text
Streamlit Paper Order UI
        |
        v
paper-order composition adapters
        |
        v
SubmitTradeService
        |
        v
TradePlanner -> ExecutionPipeline -> Volcanoes Broker port
                                      ^
                                      |
                         root paper-broker adapter
```

## Side-effect and failure boundaries

Planning, policy evaluation, and drift comparison are side-effect free. Only
`ExecutionPipeline` crossing the broker port may submit an order. The adapter
copies the broker order identifier, status, and message into generic execution
metadata. The application service maps rejection and exceptions into an
explainable result; the outer Streamlit composition preserves the existing UI
success, information, and error presentation.

The manual Paper Order path did not previously write an independent audit event.
This milestone therefore adds no audit write and preserves the broker's existing
side effects, including simulator state persistence and Alpaca paper-order
submission. Automated scanner audit logging is unchanged.

## Rollback

`USE_DETERMINISTIC_SUBMISSION = True` selects deterministic submission by
default. Setting it to `False` calls the existing
`PaperExecutionEngine.submit(proposal, confirmation)` callback unchanged. The
deterministic preview feature flag remains independent.

## Consequences and deferred work

- The default manual Paper Order submission now uses deterministic planning and
  execution boundaries.
- The current fresh-snapshot strategy detects changes before submission but does
  not claim transactional broker snapshot isolation; broker versioning is not
  available.
- Scanner execution, automated scanner audit behavior, and scanner policy
  migration are intentionally deferred.
- Alpaca internals, simulator internals, persistence schemas, analytics,
  backtesting, and policy formulas are unchanged.
