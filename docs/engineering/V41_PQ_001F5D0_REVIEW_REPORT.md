# V41-PQ-001F5D0 Review Report

## Executive summary

F5D0 completed a documentation-only Paper execution lifecycle design. It
proposes ADR-006, a minimal lifecycle state model, 30 proposed transitions,
command/event separation, replay and duplicate semantics, reconciliation entry
conditions, and the safer sequence of implementing a pure lifecycle core before
the deterministic dry-run executor.

## Starting baseline

Branch: `feature/edutrader-v4.1`.

Starting HEAD: `fbadf0dfff9b41a6f1777905bbc9aed150cd2545`.

Expected baseline: F5B execution contracts and F5C eligibility core implemented;
ADR-005 Accepted; no executor, broker port, broker adapter, execution
persistence, lifecycle state machine, runtime execution call site, or Live
support.

## Architecture review questions

1. Dedicated deterministic state machine? Yes, before any executor.
2. Pure state machine? Yes, transition decisions should be pure.
3. Separate execution state and broker state? Yes.
4. Record eligibility results as lifecycle events? Yes, explicitly.
5. Is `ELIGIBLE` a lifecycle state? No, it is an eligibility observation.
6. Minimum dry-run lifecycle? Created, eligibility recorded, approval recorded,
   would-dispatch/would-reject dry-run outcome, and no broker states.
7. States requiring persistence before broker use? All state-changing lifecycle
   states once broker side effects are possible.
8. Transitions with future side-effect intents? Dispatch, cancel dispatch, and
   replace dispatch only after future authority exists.
9. Transitions requiring reconciliation? Unknown outcome, conflicting broker
   observation, cancellation ambiguity, replacement ambiguity, restart after
   incomplete dispatch, and local/broker gaps.
10. Terminal for command versus aggregate? Command terminality and aggregate
    terminality are distinct; `REPLACED` is command-terminal but aggregate may
    continue.
11. Duplicate commands? Same ID/payload replays; same ID/different payload
    conflicts.
12. Duplicate broker observations? Safe no-op replay unless new monotonic fact.
13. Unknown outcome? Non-terminal restricted state requiring reconciliation.
14. Revision ownership? One execution aggregate owns one execution revision.
15. Dry-run isolation? Separate dry-run outcome model; no broker truth states.
16. Rollback before dispatch? `ABORTED_BEFORE_DISPATCH`.
17. Compensating actions after dispatch? None in lifecycle core; reconcile and
    possibly cancel through future authorized flow.
18. Emergency stop? Blocks future dispatch; cannot rewrite in-flight truth.
19. Broker adapter mapping? Adapters propose normalized observations only.
20. F5D implementation? F5D1 lifecycle core first; F5D2 dry-run executor second.

## Review decision

ACCEPTED WITH CONDITIONS.

ADR-006 remains Proposed and ready for separate acceptance review. The design
is sufficient to proceed to F5D1 lifecycle core, provided F5D1 remains pure and
non-executing.

## Critical findings

None.

## Major findings

- Lifecycle core must precede dry-run executor to avoid embedding transition
  rules inside the executor.
- Dry-run must not manufacture broker acknowledgements, fills, cancellations,
  replacements, or broker rejections.
- Persistence is mandatory before any broker side effect is enabled.

## Minor findings

- Existing F5B `WORKING` status should remain available but is deferred from
  the initial lifecycle state set until broker adapter mapping is reviewed.
- `RECOVERED` should be a transition outcome, not a steady state.

## Accepted decisions

- ADR-006 status is Proposed.
- Use a pure deterministic lifecycle core.
- Separate local state from broker truth.
- Record eligibility explicitly; do not mutate automatically.
- Use one aggregate-owned execution revision.
- Treat unknown outcome as non-terminal and restricted.
- Use reconciliation for ambiguity and conflict.
- Keep dry-run outcomes separate from broker truth states.

## Conditional decisions

- `IDEMPOTENCY_RESERVED` and dispatch-adjacent states require durable
  persistence before broker side effects.
- Cancellation and replacement become executable only after broker adapter,
  persistence, and reconciliation foundations exist.

## Deferred decisions

- Durable schema.
- Exact lifecycle event contract.
- Broker read/query ports.
- Reconciliation algorithm.
- Emergency-stop service integration.
- Cross-process locking.
- Live execution.

## Rejected alternatives

- Jump directly to dry-run executor.
- Jump directly to broker execution.
- Treat eligibility as lifecycle mutation.
- Treat broker acknowledgement as fill.
- Treat replacement as cancel-and-submit fallback.
- Add `DRY_RUN` to `PaperExecutionMode`.

## Acceptance conditions for F5D1

- Production code may add only pure lifecycle contracts and transition logic.
- No broker port, broker adapter, persistence, runtime wiring, simulator access,
  event publishing, metrics, logging, UI, API, CLI, configuration, dependency,
  or Live behavior.
- Architecture tests must preserve ADR-005 boundaries.

## Verification placeholder

Verification results are recorded in the final task report after `git diff
--check` and `make verify`.

## Explicit non-execution statement

F5D0 is design/documentation only. It implements no production lifecycle state
machine, executor, dry-run executor, broker port, broker adapter, persistence,
runtime wiring, event publisher, metrics, logging, UI, API, CLI, configuration,
dependency, or Live behavior.
