# V41-PQ-001F5D0 Reconciliation Entry Model

## Purpose

Define when reconciliation becomes mandatory and how recovery may re-enter the
normal lifecycle. This is design only.

## Mandatory reconciliation entry conditions

- Outcome unknown.
- Broker acknowledgement ambiguity.
- Duplicate broker references.
- Local aggregate missing broker order.
- Broker order missing locally.
- Conflicting fill quantity.
- Cancellation ambiguity.
- Replacement ambiguity.
- Restart after incomplete dispatch.
- Revision conflict.
- Conflicting observations.
- Process crash after possible broker dispatch.
- Broker status that contradicts local terminality.

## Proposed reconciliation outcomes

| Outcome | Meaning | May transition to normal lifecycle? |
|---|---|---:|
| `CONSISTENT` | Local and broker facts agree. | Yes |
| `LOCAL_AHEAD` | Local state has accepted facts not confirmed by broker. | Maybe; often requires operator action. |
| `BROKER_AHEAD` | Broker has truthful newer facts. | Yes, with recovery transition. |
| `MISSING_LOCALLY` | Broker order exists but local aggregate lacks durable fact. | Yes, after operator-reviewed recovery. |
| `MISSING_AT_BROKER` | Local dispatch fact exists but broker cannot find order. | Maybe; could become broker rejected or unresolved. |
| `CONFLICTING` | Facts cannot both be true. | No; remain reconciliation required. |
| `UNRESOLVED` | Evidence insufficient. | No |
| `OPERATOR_ACTION_REQUIRED` | Human decision needed. | Not until decision recorded. |

## Recovery transitions

Reconciliation may recover to:

- `BROKER_ACKNOWLEDGED`
- `PARTIALLY_FILLED`
- `FILLED`
- `CANCELLED`
- `BROKER_REJECTED`
- `FAILED_TERMINAL`
- `RECONCILIATION_REQUIRED`

`RECOVERED` is not a steady state. Recovery is an accepted transition with
evidence into a concrete lifecycle state.

## Read-first rule

Recovery must read durable local state and broker evidence before proposing any
transition. It must not retry a possibly dispatched command.

## Operator visibility

Every reconciliation entry must be operator-visible in future evidence. No
credentials, raw broker payloads, or account-sensitive data may appear in the
future evidence record.
