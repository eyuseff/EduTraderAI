# Project Sentinel Review: ADR-006 Paper Execution Lifecycle Acceptance

## Review identity

Review: Sentinel ADR-006 Paper Execution Lifecycle Acceptance.

Date: 2026-08-04.

Repository branch: `feature/edutrader-v4.1`.

Starting HEAD: `1f1a44de48eb2a28faee7e643ce0bdf24606a0cb`.

## Review outcome

APPROVED.

ADR-006 final status: Accepted.

F5D1 implementation readiness: READY_FOR_IMPLEMENTATION.

## Scope reviewed

- `docs/adr/ADR-006-PAPER-EXECUTION-LIFECYCLE.md`
- F5D0 state, transition, command/event, replay, reconciliation, dry-run, and
  review documents
- ADR-005 and F5A/F5B/F5C execution documents
- Implemented F5B execution contracts and F5C eligibility types

## Review questions answered

All 58 review questions passed after documentation precision findings were
closed. The execution aggregate is owned by the future lifecycle core.
Lifecycle state and broker-observation state are separate. Command inputs,
broker observations, and reconciliation observations are separate. Eligibility
and approval recording are explicit and non-authoritative. No transition
authorizes broker dispatch by itself.

## Final state inventory

Final state count: 22.

Accepted states:

`CREATED`, `ELIGIBILITY_EVALUATED`, `INELIGIBLE`,
`APPROVAL_CONFIRMED`, `IDEMPOTENCY_RESERVED`, `READY_FOR_DISPATCH`,
`DISPATCH_PENDING`, `DISPATCHED`, `BROKER_ACKNOWLEDGED`,
`PARTIALLY_FILLED`, `FILLED`, `CANCEL_REQUESTED`, `CANCEL_PENDING`,
`CANCELLED`, `REPLACE_REQUESTED`, `REPLACE_PENDING`, `REPLACED`,
`BROKER_REJECTED`, `OUTCOME_UNKNOWN`, `RECONCILIATION_REQUIRED`,
`FAILED_TERMINAL`, `ABORTED_BEFORE_DISPATCH`.

Rejected states:

`ELIGIBLE`, `RECOVERED`, `DRY_RUN_ACCEPTED`, `DRY_RUN_REJECTED`.

Deferred states:

`WORKING`, adapter-specific open statuses, routed venue states, and broker
native replace sub-states.

## Terminality model

Command-terminal states:

`INELIGIBLE`, `ABORTED_BEFORE_DISPATCH`, `BROKER_REJECTED`, `REPLACED`,
`FAILED_TERMINAL`.

Aggregate-terminal states:

`FILLED`, `FAILED_TERMINAL`, and `CANCELLED` when no remaining working broker
reference exists.

Broker-order-terminal observations:

`FILLED`, `CANCELLED`, `BROKER_REJECTED`.

`RECONCILIATION_REQUIRED` is never terminal.

## Final transition inventory

Initial transition count: 30.

Final transition count: 30.

Transition IDs: PX-TRN-001 through PX-TRN-030.

All accepted transitions increment the execution aggregate revision exactly
once. Rejected transitions, stale transitions, duplicate replays, duplicate
broker observations, and observational no-ops do not increment revision.

## Replay and duplicate rules

Same command ID plus same payload replays the original logical outcome without
mutation, revision increment, or repeated side-effect intent.

Same command ID plus different payload is a duplicate conflict.

Same idempotency key plus materially different payload is an idempotency
conflict.

Duplicate broker observations are safe no-ops unless they contain a new
monotonic fact. Conflicting broker observations require reconciliation.

## Unknown-outcome rule

`OUTCOME_UNKNOWN` covers possible dispatch with missing, ambiguous, or
contradictory outcome evidence. It is non-terminal, restricted, requires
reconciliation, prohibits blind retry, and does not assume success or failure.

## Reconciliation rules

Reconciliation entry conditions include outcome unknown, acknowledgement
ambiguity, duplicate broker references, local/broker missing-order gaps,
conflicting fill quantity, cancellation ambiguity, replacement ambiguity,
restart after incomplete dispatch, revision conflict, and conflicting
observations.

Permitted reconciliation outcomes are `CONSISTENT`, `LOCAL_AHEAD`,
`BROKER_AHEAD`, `MISSING_LOCALLY`, `MISSING_AT_BROKER`, `CONFLICTING`,
`UNRESOLVED`, and `OPERATOR_ACTION_REQUIRED`.

Permitted recovery destinations are bounded to concrete lifecycle states:
`BROKER_ACKNOWLEDGED`, `PARTIALLY_FILLED`, `FILLED`, `CANCELLED`,
`BROKER_REJECTED`, `FAILED_TERMINAL`, or continued
`RECONCILIATION_REQUIRED`.

## Cancellation model

Cancellation before dispatch is local abort. Cancellation after broker
acknowledgement or partial fill is a request, not confirmation. Cancellation
does not reverse fills. `FILLED` cannot transition to `CANCELLED`. Ambiguous
cancellation requires reconciliation.

## Replacement model

Replacement is native-only. Cancel-and-submit fallback is rejected. Replacement
request is not replacement. Replacement races with fills are handled by fill
truth winning when broker evidence proves fill before replacement. `REPLACED`
is command-terminal but not necessarily aggregate-terminal.

## Partial-fill model

Partial-fill observations are monotonic cumulative facts. Duplicate fill
observations are no-ops. Out-of-order or conflicting fill observations require
reconciliation. Full fill transitions to aggregate-terminal `FILLED`.

## Dry-run readiness

F5D1 lifecycle core may include broker states as modeled states but must not
manufacture broker truth. F5D2 dry-run should use a separate immutable dry-run
outcome contract and stop at pre-dispatch/would-dispatch semantics. Paper
environment must not be overloaded as execution-effect mode; do not add
`DRY_RUN` to `PaperExecutionMode`.

## Guard classification

F5D1 may implement deterministic in-memory guards: Paper-only mode, identity
consistency, expected revision, eligibility result compatibility, approval
evidence checks, state validity, duplicate classification, and descriptive
intent generation.

F5D1 must represent but not fake deferred guards: durable idempotency
reservation, persistence conflict detection, external emergency-stop clearance,
broker evidence, fill monotonicity from broker truth, and reconciliation
against live broker state.

## Findings summary

Critical findings: 0 open.

Major findings: 0 open, 2 closed.

Minor findings: 0 open, 3 closed.

Observations: 2 deferred, 4 closed.

## Acceptance decision

ADR-006 satisfies the acceptance requirements:

- final state inventory is explicit;
- final transition inventory is explicit;
- revision semantics are explicit;
- replay and duplicate semantics are explicit;
- unknown-outcome and reconciliation-entry semantics are explicit;
- cancellation and replacement semantics are safe;
- dry-run isolation is explicit;
- F5D1 scope is bounded;
- no unresolved critical or major lifecycle risk remains.

## Exact F5D1 authorized scope

F5D1 may implement:

- immutable lifecycle aggregate;
- lifecycle state enum;
- lifecycle input/event contracts;
- transition specification;
- pure transition function;
- apply-transition function if justified and pure;
- revision validation;
- replay/idempotency decision model;
- descriptive side-effect intents only;
- descriptive evidence intents only.

F5D1 must not implement broker ports, broker adapters, broker calls,
persistence, durable idempotency, executor, dry-run executor, runtime wiring,
simulator access, event publication, metrics, logging, UI, API, CLI,
configuration, environment switches, or Live behavior.

## Non-implementation statement

This review implemented no production lifecycle code. It performed no broker
call, no simulator access, no runtime action, and introduced no execution
authority.
