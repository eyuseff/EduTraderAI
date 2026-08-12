# V41-PQ-001F5A Market Capability Model

## Purpose

Prevent broker-specific, account-specific, symbol-specific, and venue-specific
execution rules from leaking into qualification, readiness, strategy logic, or
generic execution orchestration.

## Capability categories

| Capability | Scope | Source | Deterministic? | Runtime data? | Fail-closed behavior |
|---|---|---|---:|---:|---|
| Supported order types | broker/venue/account | static plus broker | Yes when certified | Maybe | reject unsupported or unknown. |
| Time-in-force values | broker/venue/account | static plus broker | Yes when certified | Maybe | reject unknown. |
| Fractional quantity support | broker/account/symbol | broker/account | Usually | Maybe | require integer lot if unknown. |
| Minimum lot size | venue/symbol | venue/broker | Yes with snapshot | Maybe | reject if unknown. |
| Tick size | venue/symbol/price band | venue/broker | Yes with snapshot | Maybe | reject or normalize only with explicit rule. |
| Minimum notional | broker/account/symbol | broker/account | Yes with snapshot | Maybe | reject if unknown. |
| Maximum order size | broker/account/symbol | broker/account | Yes with snapshot | Maybe | reject if exceeded or unknown. |
| Short-sale support | account/symbol/venue | broker/account | Maybe | Yes | reject short instructions initially. |
| Extended-hours support | broker/account/session | broker/session | Maybe | Yes | reject extended-hours unless explicitly supported. |
| Stop order support | broker/venue | broker/static | Yes when certified | Maybe | reject unsupported. |
| Stop-limit support | broker/venue | broker/static | Yes when certified | Maybe | reject unsupported. |
| Trailing-stop support | broker/venue | broker/static | Yes when certified | Maybe | deferred/rejected initially. |
| Replacement support | broker/order type | broker/static | Yes when certified | Maybe | reject replace unless native support proven. |
| Cancellation support | broker/order state | broker/static/status | Yes with status | Yes | query/reconcile if unknown. |
| Session status | venue/symbol | market clock | No, time-dependent | Yes | reject or require explicit session snapshot. |
| Symbol tradability | broker/symbol | broker/venue | Maybe | Yes | reject unknown. |
| Asset class | symbol | broker/venue | Yes with snapshot | Maybe | reject unsupported. |
| Currency | symbol/account | broker/venue/account | Yes with snapshot | Maybe | reject unsupported. |
| Venue | symbol/order route | broker/venue | Maybe | Yes | reject unknown venue. |
| Account permissions | account | broker | No, account-specific | Yes | reject unknown. |

## Capability decision

Future `MarketCapabilityDecision` should include:

- allowed/denied/unknown;
- safe reason code;
- capability snapshot identifier;
- source type, such as static certification, broker account snapshot, symbol
  metadata, venue session, or manual configuration;
- timestamp;
- expiry/staleness policy;
- redacted explanation;
- fields validated.

Unknown is not advisory for state-changing execution. Unknown means fail
closed.

## Deterministic versus runtime facts

Deterministic with versioned fixtures or static certification:

- allowed order type set;
- supported time-in-force values;
- integer quantity requirement;
- unsupported operations such as multi-leg or Live;
- whether native replacement exists for a broker/order class, once certified.

Runtime-dependent:

- market session;
- tradability;
- account permissions;
- account restrictions;
- rate-limit posture;
- symbol-specific halts or broker restrictions;
- current broker order state for cancellation/replacement.

The execution command should include the capability decision fingerprint used
for approval, but state-changing execution should refresh or validate stale
capability facts where required by policy.

## Broker and venue isolation

Qualification may say a scenario reached a qualified Paper intent. It should
not know Alpaca-specific request objects, future Chilean broker request
objects, account endpoints, local venue sessions, lot-size rules, or tick-size
tables.

Adapters and capability providers absorb those details and return normalized
decisions to the execution application layer.

## Chilean-market extensibility note

Future Chilean-market support should be implemented by adding:

- a Chile-specific broker adapter;
- a Bolsa de Santiago or broker-specific capability provider;
- local session and holiday data;
- local lot-size and tick-size rules;
- local short-sale and asset-permission handling;
- local reporting and settlement metadata;
- broker-specific authentication isolation.

Current qualification and readiness components should remain unchanged. This
document does not assert Chilean legal, regulatory, settlement, or market-rule
requirements. A separate cited regulatory review is required before any
implementation.

## Initial recommendation

F5B should define capability request/decision/failure contracts only. F5C may
consume capability decisions for pure eligibility. Broker-sourced runtime
capability retrieval belongs later in adapter certification and controlled
Paper execution slices.
