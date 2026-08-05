# V41-PQ-001F5D0 Dry-Run Executor Plan

## Purpose

Define what the future deterministic dry-run executor may do after the
lifecycle core exists. This is design only.

Sentinel review status: accepted as part of ADR-006 acceptance on 2026-08-04.

## Recommended approach

Use a separate dry-run outcome model rather than entering broker-truth states.
Do not add `DRY_RUN` to `PaperExecutionMode`, because that enum currently
represents trading environment, not execution effect.

## Future dry-run executor may represent

- command evaluated;
- command eligible;
- command ineligible;
- command indeterminate;
- would dispatch;
- would reject;
- would require external evidence;
- deterministic dry-run receipt;
- deterministic dry-run failure;
- no broker action taken;
- no runtime authority created.

## Future dry-run executor must not represent

- broker order accepted;
- exchange order accepted;
- actual fill;
- actual cancellation;
- actual replacement;
- actual broker rejection;
- actual broker availability;
- actual account capability;
- actual market session status.

## Proposed F5D1 prerequisite

Before F5D2 dry-run executor, implement F5D1 lifecycle core:

- immutable lifecycle aggregate;
- immutable lifecycle input;
- immutable transition decision;
- pure transition function;
- deterministic revision handling;
- replay and duplicate classification;
- no executor;
- no broker;
- no persistence;
- no runtime wiring.

## Proposed F5D2 responsibilities

After F5D1, F5D2 may:

- consume immutable F5B commands;
- consume F5C eligibility results;
- record lifecycle inputs through the pure lifecycle core;
- produce dry-run-only outcomes;
- classify would-dispatch versus would-reject;
- prove no broker-truth states are manufactured;
- prove no side effect is performed.

## Deferred beyond F5D2

- Durable persistence and idempotency foundation.
- Broker adapter certification.
- Broker read/query contracts.
- Controlled Paper broker submission.
- Reconciliation implementation.
- Event publication, metrics, UI/API/CLI, and Live support.

## Non-authorization

This plan does not implement or authorize a dry-run executor. It only defines
future responsibilities and boundaries.
