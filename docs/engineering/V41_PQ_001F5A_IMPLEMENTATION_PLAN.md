# V41-PQ-001F5A Implementation Plan

## Purpose

Define the safest implementation sequence after the F5A architecture review.
No future slice is marked implemented by this document.

## Recommended slice sequence

### V41-PQ-001F5B — Paper Executor Contracts

Scope:

- immutable contract records;
- enums;
- typed safe failures;
- deterministic identities and fingerprints;
- Paper-only mode marker;
- no broker;
- no runtime wiring.

Acceptance:

- contracts are immutable;
- no `LIVE` execution mode is exposed;
- no credentials or raw broker payloads are allowed;
- same command payload produces deterministic fingerprint;
- same command id with changed payload is representable as conflict;
- qualification/readiness do not import execution contracts unless an explicit
  application boundary is approved.

### V41-PQ-001F5C — Executor Policy and Eligibility Core

Scope:

- pure command eligibility;
- Paper-only validation;
- approval validation;
- expected execution revision validation;
- market-capability contract consumption;
- emergency-stop input contract;
- no broker.

Acceptance:

- readiness never authorizes execution;
- stale revision rejected before dispatch;
- missing approval rejected before dispatch;
- unknown capability fails closed;
- no runtime wiring.

### V41-PQ-001F5D — Deterministic Dry-Run Executor

Scope:

- deterministic simulated receipts;
- no simulator state;
- no broker;
- no runtime authority.

Acceptance:

- dry-run receipts cannot be mistaken for broker receipts;
- dry-run mode cannot create orders;
- idempotent replay is deterministic.

### V41-PQ-001F5E — Persistence and Idempotency Foundation

Scope:

- durable command identity;
- payload fingerprint uniqueness;
- logical execution identity;
- optimistic execution revision;
- idempotency reservation;
- append-only local history;
- no broker execution.

Acceptance:

- process restart does not permit duplicate command dispatch;
- stale revisions fail safely;
- transaction boundary is documented and tested.

### V41-PQ-001F5F — Paper Broker Adapter Certification Harness

Scope:

- fake transport or sandbox certification harness;
- adapter contract tests;
- receipt normalization;
- Paper endpoint proof;
- no production runtime wiring.

Acceptance:

- adapter cannot select Live;
- credentials are not logged;
- broker exceptions become typed failures;
- acknowledgement, rejection, query, cancel, and replace capabilities are
  classified.

### V41-PQ-001F6A — Controlled Paper Broker Submission

Scope:

- explicit guard;
- disabled by default;
- Paper only;
- one controlled call site;
- no Live.

Acceptance:

- operator approval required;
- no dual authority with legacy;
- idempotency and revision persistence enabled first;
- timeout creates unknown outcome;
- broker submission evidence is redacted and immutable.

### V41-PQ-001F6B — Reconciliation and Recovery

Scope:

- startup reconciliation;
- timeout reconciliation;
- post-error reconciliation;
- local/broker state comparison;
- operator-action classification.

Acceptance:

- no duplicate execution during recovery;
- unresolved outcomes block state-changing commands;
- recovery is auditable.

### V41-PQ-001F6C — Execution Observation and Audit

Scope:

- execution events;
- audit records;
- operational metrics;
- redaction;
- evidence export.

Acceptance:

- authoritative state transitions and observations are distinct;
- publisher failure does not cause duplicate broker orders;
- audit gaps are incident-worthy.

### V41-PQ-001F7 — Parallel Authority Validation

Scope:

- compare legacy and new executor authority without dual submission;
- prove one authority at a time;
- rollback flag evidence.

Acceptance:

- no dual broker order creation;
- legacy rollback remains available;
- mismatches are classified before cutover.

### V41-PQ-001F8 — Legacy Retirement Review

Scope:

- decide whether legacy Paper execution can be retired;
- require evidence, incidents, rollback history, and operator approval.

Acceptance:

- no unresolved high/critical execution risks;
- reconciliation and persistence are proven;
- operator explicitly approves cutover.

## Deployment strategy

Do not deploy broker side effects until contracts, eligibility, dry-run,
persistence, idempotency, adapter certification, explicit approval, and
reconciliation are complete.

## Rollback strategy

- Before F6A, rollback is documentation/code-path removal only because no broker
  side effects exist.
- At F6A, one explicit runtime guard must disable the new executor and leave
  legacy authority intact.
- After broker dispatch, rollback is not possible; reconciliation and
  compensating actions are the recovery tools.

## Required future ADRs

- Paper Execution Command and State Machine ADR.
- Execution Persistence and Idempotency ADR.
- Broker Adapter Certification ADR.
- Reconciliation and Recovery ADR.
- Emergency Stop and Approval ADR.
- Live Trading Isolation ADR, only if Live is proposed.

## Non-authorization

This plan does not authorize implementation beyond the next separately approved
slice. It does not authorize broker execution, runtime wiring, Live behavior,
or legacy cutover.
