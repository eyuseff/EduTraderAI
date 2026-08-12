# ADR-0002: PolicyParity Milestone

- Status: Accepted
- Date: 2026-07-20

## Context

The deterministic Preview Trade path initially shared sizing and risk code with
`ExecutionPipeline`, but it did not share every policy enforced by the active
legacy paper preview. Minimum price, minimum reward/risk, duplicate positions,
and duplicate open orders existed only in the legacy manager. Daily loss used
a different equity base. Capital limits rejected a risk-sized deterministic
trade while the legacy preview reduced quantity to the smallest permitted
capacity.

Those differences made the deterministic preview unsuitable as the policy
authority for a future execution migration, even though its calculations were
pure and repeatable.

## Decision

Trade planning policies are explicit immutable objects. Each policy consumes
an immutable `TradePolicyContext` and returns an immutable `PolicyDecision`
containing a stable code and human-readable explanation.

The PolicyParity milestone introduces:

- `MinimumPricePolicy`;
- `RewardRiskPolicy`;
- `DuplicatePositionPolicy`;
- `DuplicateOrderPolicy`;
- `BuyingPowerPolicy`; and
- `DailyLossPolicy`.

The existing position-size, open-position, and portfolio-exposure rules are
also represented as explicit policies because their quantity-limit behavior is
required for exact parity.

`TradePlanner` owns no policy-specific branching or rule sequence. It sizes the
trade, evaluates the ordered immutable `TradePolicySet`, applies the smallest
quantity cap, and returns an immutable `TradePlan` with ordered explanations.

## Configuration Profiles

The default policy set preserves the existing deterministic execution
semantics: capital violations reject, daily loss uses starting equity, and
adding to an existing position is allowed. This keeps `ExecutionPipeline`
behavior unchanged.

The Paper Order preview adapter supplies a parity policy set configured from
the root `RiskLimits` values. In that profile:

- daily loss uses current equity;
- buying power, maximum position value, and exposure cap quantity;
- minimum price and reward/risk are enforced;
- duplicate positions and duplicate orders are rejected;
- all rejection explanations are collected in legacy order; and
- a zero quantity uses the legacy explanation.

Legacy modules are not imported into the deterministic core. Their thresholds
are boundary configuration values only.

## Order Snapshot Boundary

Duplicate-order policy requires current open-order symbols. The outer preview
adapter reads this broker state and passes an immutable normalized set into
`PreviewTradeService`. Neither the application service, `TradePlanner`, nor any
policy imports a broker implementation.

## Parity Definition

For valid buy proposals under equivalent configuration, parity means equality
of:

1. quantity;
2. dollar risk;
3. position exposure;
4. approval;
5. reward/risk; and
6. ordered rejection explanations.

The automated parity matrix covers approvals, every explicit parity policy,
capital caps, zero capacity, daily-loss boundaries, open-position limits,
combined rejections, and non-default configuration. Every matrix case compares
the deterministic result directly with the legacy `RiskDecision`.

## Dependency Rule

Policies and planning remain inside Volcanoes and may import only inward core
contracts. They must not import Streamlit, root broker modules, root trading
modules, adapters, scanners, or persistence.

## Deferred Work

This milestone does not replace submission or execution. The Streamlit Paper
Order confirmation still calls `PaperExecutionEngine.submit()`, which performs
its existing legacy risk check before submitting. Scanner, Alpaca, persistence,
and execution migrations remain deferred.

## Consequences

- Preview policy behavior is deterministic and independently testable.
- Policy order is configuration rather than hidden control flow.
- The active buy preview can reach exact legacy parity without importing
  infrastructure into application or core modules.
- Execution retains its current behavior until a separately approved migration.
- Open-order parity adds one read-only broker snapshot call during preview.
