# V41-PQ-001F5E0 Restart and Recovery Model

## Purpose

Define restart behavior required before broker execution. This is design only.

## Startup scan

Future startup recovery must scan durable aggregates in states that can require
attention:

- `DISPATCH_PENDING`
- `DISPATCHED`
- `OUTCOME_UNKNOWN`
- `RECONCILIATION_REQUIRED`
- `CANCEL_PENDING`
- `REPLACE_PENDING`
- `PARTIALLY_FILLED`

## State recovery table

| State | Automatic progression | Required recovery |
|---|---:|---|
| `DISPATCH_PENDING` | Prohibited unless dispatch claim proves no broker call occurred | Inspect durable dispatch intent and worker claim; otherwise reconcile |
| `DISPATCHED` | Prohibited | Read-only broker status or reconciliation |
| `OUTCOME_UNKNOWN` | Prohibited | Reconciliation required |
| `RECONCILIATION_REQUIRED` | Prohibited | Operator-visible reconciliation workflow |
| `CANCEL_PENDING` | Prohibited | Read-only broker status; fill/cancel race handling |
| `REPLACE_PENDING` | Prohibited | Read-only broker status; fill/replace race handling |
| `PARTIALLY_FILLED` | Limited | New commands require current broker/account evidence |

## Crash after possible broker acceptance

If a crash occurs after a broker request may have crossed the boundary, the
system must not resubmit blindly. It must preserve ambiguity and use read-only
broker evidence or operator reconciliation.

## Worker claims

Future dispatch workers should have durable claim identity, claim timestamp,
and expiration semantics. Expired claims may permit another worker to inspect
state, not to blindly submit.

## New command blocking

New commands for an aggregate in ambiguous or in-flight states must be blocked
or routed to reconciliation until current truth is established.

## Operator visibility

Unknown, reconciliation-required, and in-flight recovery states must be visible
to operators with safe reason codes and no credential leakage.

## Source-of-truth rule

Local durable state represents expected local lifecycle truth. Broker truth is
external and must be observed, not inferred.
