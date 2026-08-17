# ADR-012 Acceptance Record

Date: 2026-08-16
Decision owner: repository owner authorization in the active v4.1 automation session
Status: Accepted for the current v4.1 supported topology

## Decision

ADR-012, `Durable Execution Coordination Authority`, is accepted as the architecture direction for v4.1.

The accepted decision is narrowly scoped:

- the existing durable execution database authority remains the single source of consequential coordination truth;
- process-local supervisor locks/state remain advisory only and never grant execution authority;
- Redis or a separate distributed lock service is not introduced as an execution-authority source for the current topology;
- SQLite remains the authoritative adapter only for the currently supported local durable topology;
- no multi-host support is claimed by this acceptance;
- if multi-host execution becomes a supported requirement, the preferred evolution is a transactional server-database adapter implementing the same storage-neutral authority contracts and fencing semantics, with separate migrations, adversarial tests, operational validation, and approval before support is claimed;
- an outbox may later be introduced only as a non-authoritative notification mechanism; delivery never grants broker-effect permission.

This acceptance supersedes only ADR-012's proposal-only governance paragraph. All technical limits, topology constraints, fencing rules, failure semantics, and migration requirements in ADR-012 remain binding.

## Evidence considered

Acceptance is based on the repository evidence accumulated through v4.1, including durable command/idempotency/CAS authority, dispatch control generation, durable claim/authorization/resolution, restart discovery, recovery/reconciliation, competing-worker tests, stale/terminal-worker rejection, pre-commit and post-CAS crash-window rollback tests, record-fingerprint integrity checks, and fail-closed runtime startup validation.

PR #67 additionally closed the remaining known RECONCILE transition-record fingerprint gap before this decision was recorded.

## Explicit non-claims

This acceptance does not authorize or claim:

- multi-host execution support;
- SQLite over a network/shared filesystem;
- Redis-based execution authority;
- automatic claim expiry or timeout redispatch;
- broker credential access;
- external Paper or Live order submission;
- production `state/` access;
- release tagging, deployment, or artifact publication.

## External event transport decision

For v4.1, selection and connection of an external event transport is **deferred and not required for release qualification**. The transport-neutral contract and observability/retry layer remain the approved boundary. A concrete vendor/backend should be selected only when an operational requirement exists, through a separate decision and implementation review.

## Follow-up

With ADR-012 accepted and external event transport deferred, the remaining v4.1 gate tracked by issue #69 is connected Paper qualification evidence. That evidence must still be produced through the separately controlled Paper consequential-action boundary and cannot be inferred from this architecture decision.
