# ADR-V41-003 - Event Publisher Observability

## Status

PROPOSED

## Context

EduTraderAI v4.1 planning starts from the v4.0.0 Stable release. This ADR is a
placeholder for evidence-backed decision work. No architecture has been selected
by this initialization document.

## Decision drivers

- Preserve v4.0 Paper workflow compatibility.
- Keep safety controls deterministic and testable.
- Avoid implicit live-trading capability.
- Preserve architecture boundaries.
- Require redacted evidence before release qualification.

## Options to evaluate

- Retain `NullEventPublisher` for local/test use only.
- File-backed local publisher.
- Database-backed event publisher.
- External queue or stream publisher.
- Hybrid local audit plus external delivery adapter.


## Safety considerations

- Fail closed when a safety precondition is not met.
- Avoid credentials, account identifiers, and raw broker payloads in evidence.
- Preserve explicit operator confirmation where broker actions are involved.
- Prevent duplicate execution and stale state from creating orders.

## Compatibility considerations

- Existing v4.0 Paper workflows must remain compatible unless separately
deprecated.
- Existing evidence formats should remain readable.
- New evidence schemas must be versioned.
- Migrations require rollback instructions.

## Evidence required before decision

- Option comparison.
- Architecture boundary review.
- Unit and integration test plan.
- Operational evidence plan.
- Failure-mode analysis.

## Decision

NOT YET MADE
