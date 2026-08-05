# ADR-006: Paper Execution Lifecycle

## 1. Title

Paper Execution Lifecycle.

## 2. Status

Proposed.

## 3. Date

2026-08-04.

## 4. Context

ADR-005 accepted the Paper execution model and the advisory eligibility core.
F5B implemented inert Paper execution contracts. F5C implemented advisory
eligibility. The next implementation work needs a formally reviewed lifecycle
before any dry-run executor or broker-facing execution path exists.

## 5. Problem

Paper execution needs deterministic state ownership, revision behavior,
duplicate handling, unknown-outcome behavior, cancellation semantics,
replacement semantics, and reconciliation entry points. Without a lifecycle
model, later executor work could confuse local truth, broker truth, eligibility
observations, receipts, and failure facts.

## 6. Decision proposal

Define a pure deterministic Paper execution lifecycle as a future aggregate
state machine. The lifecycle records local execution state, accepts explicit
inputs, produces transition decisions and future evidence intents, and never
performs broker work itself.

## 7. Execution lifecycle ownership

The execution lifecycle core owns local aggregate state and execution revision.
The persistence/idempotency layer owns durable reservation and replay lookup.
Broker adapters own normalized broker observations only. Reconciliation owns
read-only comparison and recovery proposals. Operators and approval boundaries
own approval evidence. Emergency-stop services may block future transitions but
do not rewrite broker truth.

## 8. Relationship to ADR-005

ADR-006 builds on ADR-005. It does not replace ADR-005 and does not transfer
execution authority. ADR-005 remains Accepted.

## 9. Relationship to eligibility

Eligibility is not lifecycle mutation. Eligibility does not create a submitted
state. `ELIGIBLE` may be recorded later as evidence through an explicit
`RECORD_ELIGIBILITY` input, but it does not authorize execution or dispatch.

## 10. Relationship to future persistence

The lifecycle can be pure in memory, but production execution requires
persistence before broker side effects: durable aggregate state, revision,
command payloads, idempotency records, receipts, failures, and reconciliation
history.

## 11. Relationship to broker observations

Broker observations are facts observed through future adapters. Dispatch is not
broker acknowledgement. Acknowledgement is not fill. Partial fill is not full
fill. Broker observations may propose transitions but do not mutate state
without lifecycle acceptance.

## 12. Local state versus broker state

Local state records what the platform has accepted. Broker state records what
the broker reports. When local and broker facts conflict, broker truth is not
silently overwritten into local state; reconciliation is required.

## 13. Command model

Commands are immutable F5B Paper execution commands. Command creation is not
dispatch. Future lifecycle commands include recording eligibility, approval,
idempotency reservation, dispatch preparation, dispatch recording, broker
observation recording, cancellation request, replacement request, unknown
outcome marking, reconciliation, pre-dispatch abort, and terminal failure.

## 14. Event model

Lifecycle events are append-only future evidence records for accepted
transitions. Broker observations are not application commands. Reconciliation
observations are read-only comparison facts until explicitly accepted.

## 15. Transition authority

Only the lifecycle transition function may accept a transition. No state
transition authorizes broker execution by itself. Side-effect intents, when
future slices introduce them, must be interpreted by an outer authorized
orchestrator.

## 16. Revision behavior

One aggregate owns its own execution revision. Qualification revision remains
separate. Proposed invariant: each accepted lifecycle transition increments the
execution aggregate revision exactly once. Replays, duplicate observations,
rejected transitions, stale commands, and no-op inputs do not increment
revision.

## 17. Replay behavior

Same command ID and same payload replays the original logical outcome without a
second mutation or side-effect intent. Different command ID with the same
idempotency key and same logical payload is logical idempotency replay.

## 18. Duplicate behavior

Same command ID with different payload is a hard duplicate conflict. Same
idempotency key with materially different payload is an idempotency conflict.
Duplicate broker observation is a safe observational replay.

## 19. Unknown-outcome behavior

Timeout after possible dispatch produces `OUTCOME_UNKNOWN`. The lifecycle must
not assume success, assume failure, or resubmit automatically. Unknown outcome
requires reconciliation and restricts further state-changing commands.

## 20. Reconciliation requirement

Reconciliation is mandatory for outcome unknown, broker acknowledgement
ambiguity, duplicate broker references, local/broker missing-order gaps,
conflicting fill quantities, cancellation ambiguity, replacement ambiguity,
restart after incomplete dispatch, revision conflict, and conflicting
observations.

## 21. Cancellation semantics

Cancellation request is not cancellation. Cancellation cannot reverse completed
fills. Filled state cannot transition to cancelled. Partially filled then
cancelled must retain cumulative fill facts and cancel only the remaining
quantity when broker evidence proves cancellation.

## 22. Replacement semantics

Replacement request is not replacement. The initial design supports native
broker replace only and no cancel-and-submit fallback. Replacement retains
logical aggregate identity, uses a new command identity and idempotency key, and
must preserve traceability of old and new broker references.

## 23. Partial-fill semantics

Partial fill is non-terminal and records cumulative filled quantity, remaining
quantity, average fill price when available, observation identity, ordering, and
conflict detection. Partial fill can race with cancellation or replacement and
may require reconciliation.

## 24. Recovery semantics

Recovery is read-first: load durable local state, query broker evidence through
future read ports, compare facts, produce reconciliation outcome, and then
advance only through permitted recovery transitions. If facts cannot prove a
safe state, remain unresolved.

## 25. Terminal states

Terminal command states include `INELIGIBLE`, `ABORTED_BEFORE_DISPATCH`,
`BROKER_REJECTED`, `FILLED`, `CANCELLED`, and `FAILED_TERMINAL`. Aggregate
terminality differs from command terminality; `REPLACED` is terminal for the
replace command but not necessarily for the aggregate.

## 26. Concurrency rules

One aggregate may have at most one in-flight state-changing command. Expected
execution revision is required for state-changing inputs. Legacy and new
execution authority must never both submit the same logical order.

## 27. Emergency-stop interaction

Emergency stop blocks new future dispatch preparation after it becomes visible.
If dispatch may already have crossed the broker boundary, emergency stop cannot
rewrite the fact; the outcome must be reconciled.

## 28. Legacy coexistence

Legacy execution remains authoritative until a later controlled migration. No
new lifecycle state may be consumed by runtime dispatch in this design slice.

## 29. Consequences

The model separates local lifecycle state, broker truth, eligibility evidence,
receipts, failures, and reconciliation. It delays broker execution until a
state machine, dry-run behavior, persistence, and reconciliation are designed
and implemented.

## 30. Risks

- Future implementers may overstate dry-run facts as broker truth.
- Missing persistence would make revision and idempotency guarantees
  process-local only.
- Unknown outcomes remain operationally heavy until reconciliation exists.

## 31. Alternatives considered

- Treat F5B `PaperExecutionStatus` as the production lifecycle without review.
- Let eligibility directly create dispatch-ready state.
- Jump directly to a dry-run executor.
- Jump directly to broker execution.

## 32. Rejected alternatives

Those alternatives were rejected because they collapse advisory facts into state
mutation, combine broker truth with local truth, or introduce side-effect risk
before lifecycle semantics are settled.

## 33. Deferred decisions

Deferred decisions include durable storage schema, exact event schema, broker
read-port contracts, reconciliation implementation, emergency-stop integration,
cross-process locking, dry-run receipt types, and Live execution.

## 34. Implementation sequence

Recommended sequence: F5D1 lifecycle core, F5D2 deterministic dry-run executor,
F5E persistence and idempotency foundation, F5F Paper broker certification
harness, F6A controlled Paper broker submission, and F6B reconciliation.

## 35. Non-authorization statement

ADR-006 is Proposed and design-only. It does not authorize broker execution,
runtime dispatch, executor implementation, dry-run executor implementation,
persistence, durable idempotency reservation, broker ports, broker adapters,
runtime wiring, event publication, metrics, logging, UI, API, CLI,
configuration changes, environment switches, Live behavior, or simulator use.
