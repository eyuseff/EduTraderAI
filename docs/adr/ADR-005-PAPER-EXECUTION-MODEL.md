# ADR-005: Paper Execution Model

## 1. Title

Paper Execution Model.

## 2. Status

Accepted.

## 3. Date

2026-07-30.

## 4. Context

V41-PQ-001F5A established that Paper execution must be a separate bounded
context from qualification. V41-PQ-001F5B implemented inert immutable execution
contracts. V41-PQ-001F5C adds a deterministic eligibility core over those
contracts.

## 5. Problem

The platform needs a safe path from qualified Paper observations toward future
Paper execution without allowing readiness evidence, approval evidence, or
eligibility evaluation to become runtime execution authority.

## 6. Decision

EduTraderAI defines a Paper-only execution bounded context with immutable
commands, approvals, receipts, failures, identities, policy snapshots, canonical
serialization, deterministic fingerprints, and an advisory eligibility core.
The governing rule is: evaluate eligibility, authorize nothing, execute
nothing.

## 7. Execution bounded-context boundary

Execution contracts live under `volcanoes/application/execution`. They are
application-layer data contracts and pure evaluators. They do not import
adapters, brokers, scanners, supervisors, persistence, event publishers,
metrics, logging, HTTP clients, broker SDKs, or Streamlit.

## 8. Relationship to qualification

Qualification is not execution. Qualification state and evidence may describe a
Paper qualification workflow, but qualification results do not execute orders
and do not authorize execution.

## 9. Relationship to readiness

Qualification readiness is not execution authority. `READY_FOR_NEXT_PHASE` is an
advisory readiness signal only and must not be consumed by execution eligibility
as approval or authorization.

## 10. Command identity model

Each command has a stable command identity distinct from the aggregate identity,
correlation identity, idempotency key, and payload fingerprint.

## 11. Payload fingerprint distinction

The command payload fingerprint identifies immutable command content, excluding
the command identity. It is not a broker order identifier, persistence key, or
authorization token.

## 12. Correlation identity

Correlation identity links related preview, qualification, eligibility, and
future execution evidence for reconstruction. It does not imply authority.

## 13. Aggregate identity

Aggregate identity represents the Paper execution aggregate being operated on.
Cancel and replace commands retain aggregate identity without assuming a stored
aggregate exists in this slice.

## 14. Idempotency identity

Idempotency identity is deterministic command evidence. F5C does not reserve it
durably, query storage, or prove uniqueness across processes.

## 15. Execution revision

Execution revision is separate from qualification revision. Submit commands
begin at revision zero. Cancel and replace revisions are represented without
storage lookup in F5C.

## 16. Approval as evidence

Approval evidence records who or what approved a command and what fingerprint it
is bound to. Approval evidence is not runtime dispatch and does not authorize
broker submission by itself.

## 17. Commands as inert immutable data

Commands remain inert immutable data. They expose no `execute`, `submit`,
`dispatch`, `persist`, `reserve`, `retry`, or `reconcile` behavior.

## 18. Receipts as normalized observations

Receipts are immutable normalized observations of future execution lifecycle
facts. They do not perform broker work.

## 19. Failures as normalized immutable data

Failures are immutable normalized records of execution failure facts. They avoid
raw exceptions as stable public evidence.

## 20. Canonical serialization

Execution contracts use centralized canonical serialization so deterministic
fingerprints are stable across equivalent inputs.

## 21. Deterministic fingerprinting

Execution command payloads, approvals, policy snapshots, receipts, failures,
eligibility policies, and eligibility results use prefixed SHA-256 fingerprints.
F5C uses `pep-` for eligibility policies and `per-` for eligibility results.

## 22. Paper-only structural isolation

Paper mode is structurally isolated. Current execution commands accept only
`PaperExecutionMode.PAPER`.

## 23. Live exclusion

Live support is excluded. Any Live execution support requires a separate future
ADR, explicit approval, and new safety gates.

## 24. Eligibility versus authorization

Eligibility is not execution authority. `ELIGIBLE` means only that the command
satisfies deterministic criteria in the provided immutable policy.

## 25. Broker isolation

Broker adapters remain infrastructure-only. The execution core and eligibility
core do not import concrete brokers or broker SDKs.

## 26. Persistence expectations

Future execution will need persistence for durable idempotency, optimistic
revision checks, lifecycle evidence, and reconciliation. F5C implements none of
that persistence.

## 27. Unknown-outcome requirement

Unknown broker outcomes must be represented explicitly and require
reconciliation rather than silent success or silent failure.

## 28. Reconciliation requirement

Future execution stages must reconcile ambiguous broker outcomes against broker
evidence. F5C does not perform reconciliation.

## 29. Cancellation semantics

Cancellation does not reverse fills. A cancellation result can only describe the
broker's cancellation outcome and any remaining reconciliation need.

## 30. Replacement semantics

Replacement does not default to cancel-and-submit. Replace is a distinct
operation whose lifecycle and broker semantics must be modeled explicitly.

## 31. Consequences

The model creates a narrow, testable path from immutable commands to future
execution while keeping runtime authority outside the eligibility core.

## 32. Positive consequences

- Execution contracts are deterministic and safe to inspect.
- Eligibility can be tested without brokers, files, clocks, or environment.
- Readiness cannot silently become execution authority.
- Future executor work has explicit boundaries.

## 33. Negative consequences

- F5C cannot answer broker, market, account, risk, persistence, or readiness
  questions.
- External requirements can produce `INDETERMINATE` results until separate
  immutable evidence contracts exist.

## 34. Risks

- Operators may misread `ELIGIBLE` as permission to submit.
- Future slices may be tempted to reuse readiness as authority.
- Durable idempotency and stale-revision checks remain pending.

## 35. Alternatives considered

- Let qualification readiness authorize execution.
- Put broker checks inside eligibility.
- Implement broker execution immediately.
- Share root broker adapters directly with the execution core.

## 36. Rejected alternatives

Those alternatives were rejected because they collapse advisory evidence into
runtime authority, add hidden side effects, or couple deterministic core code to
infrastructure.

## 37. Future ADR requirements

Separate ADRs are required before Live execution, durable execution persistence,
distributed idempotency reservation, broker adapter authority, reconciliation
automation, or multi-process execution authority.

## 38. Compliance rules

- UI and adapters may depend inward on application execution contracts.
- Execution contracts and eligibility must not depend outward on adapters,
  brokers, scanners, supervisors, persistence, events, logging, metrics, HTTP,
  broker SDKs, environment, or runtime wiring.
- One execution authority may exist at a time.
- No implementation slice automatically transfers authority.

## 39. Non-authorization statement

ADR-005 authorizes only the Paper execution model and the pure advisory
eligibility core. It does not authorize broker submission, runtime dispatch,
persistence, durable idempotency reservation, stale-revision storage checks,
market checks, account checks, risk checks, emergency-stop checks, retries,
timeouts, reconciliation, scanner changes, supervisor changes, UI changes,
configuration changes, or Live behavior.
