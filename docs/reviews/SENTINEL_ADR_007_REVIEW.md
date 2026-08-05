# Project Sentinel Review: ADR-007 Execution Persistence and Idempotency

## Review identity

Review: Sentinel ADR-007 Execution Persistence and Idempotency.

Date: 2026-08-05.

Repository branch: `feature/edutrader-v4.1`.

Starting HEAD: `a6e5cba3c9d927b5a6356d931927d7914199f911`.

## Review outcome

APPROVED.

ADR-007 final status: Accepted.

Storage-technology position: `AUTHORIZE_COMPARATIVE_SPIKE`.

F5E1 readiness: `READY_WITH_CONDITIONS`.

F5E1A readiness: `READY_FOR_IMPLEMENTATION`.

F5E1B readiness: `READY_FOR_IMPLEMENTATION`.

Broker-execution readiness: `NOT_AUTHORIZED`.

## Scope reviewed

- `docs/adr/ADR-007-EXECUTION-PERSISTENCE-AND-IDEMPOTENCY.md`.
- F5E0 durable data model, transaction, idempotency, concurrency, restart, storage, migration, security, and implementation-plan documents.
- ADR-005 and ADR-006 execution model/lifecycle documents.
- Sentinel ADR-006 review and failure matrix.
- F5D1 lifecycle-core and F5D2 dry-run implementation reports.
- Current implementation under `volcanoes/application/execution/`.
- Existing SQLite helpers, portfolio repository, qualification in-memory repositories, JSONL audit, event publisher, and release/evidence documentation.

## Scope explicitly excluded

No persistence ports, repositories, units of work, database schemas, migrations, durable idempotency, broker ports, broker adapters, runtime wiring, reconciliation services, event publishers, metrics, logging, UI/API/CLI behavior, Live behavior, or simulator mutation were implemented or authorized by this review.

## Current implementation facts

- `volcanoes/application/execution/lifecycle` implements a pure immutable lifecycle aggregate, transition table, transition function, replay/conflict decisions, and descriptive side-effect/evidence intents.
- `volcanoes/application/execution/dry_run` composes eligibility and lifecycle logic but keeps `execution_authorized`, `action_executed`, and broker access false.
- `volcanoes/database` contains generic SQLite helpers and legacy-style tables, but no accepted execution aggregate, command, idempotency, journal, reconciliation, or broker-reference execution store.
- `volcanoes/portfolio/repository.py` persists portfolio snapshots and positions only.
- `volcanoes/application/qualification/in_memory.py` provides deterministic non-durable fake repositories for qualification harnesses.
- `audit/trade_log.py` writes JSONL support evidence and is not operational execution authority.
- `volcanoes/events/publisher.py` still defaults to `NullEventPublisher`, which has no durable delivery semantics.
- `state/simulated_broker.json` is unrelated mutable simulator runtime state and is not authoritative execution persistence.

## Source-of-truth model

Final hierarchy:

1. Immutable execution command record — source of truth for what was requested.
2. Execution aggregate snapshot — local source of truth for current expected lifecycle state.
3. Append-only transition journal — source of truth for accepted local state transitions.
4. Normalized broker observations — source of truth for received external broker facts.
5. Reconciliation record — source of truth for how disagreement was resolved.
6. Audit/evidence material — supporting evidence, not operational authority.
7. Dry-run results — simulation-only and never authoritative.
8. Simulator JSON state — unrelated runtime state and never authoritative for execution persistence.

Rejected authority paths: raw broker state overwriting history, audit logs replacing aggregate state, dry-run results becoming execution state, simulator state becoming broker truth, mutable command payloads, and reusable/deletable idempotency records after broker effects.

## Mandatory review questions

All 65 mandatory questions passed. Summary:

| Range | Result | Summary |
|---|---|---|
| 1-5 | PASS | Persistence is separate infrastructure beneath the execution application layer; local aggregate and broker truth are separated; snapshot and journal are separate; full event sourcing is explicitly rejected for now. |
| 6-12 | PASS | Command and idempotency fingerprints are permanent; exact replay/conflict and idempotency replay/conflict are deterministic across restarts once persisted. |
| 13-20 | PASS | Uniqueness, aggregate CAS, stale-write fail-closed behavior, revision-neutral replay/reject behavior, and separation from qualification/broker revisions are explicit. |
| 21-28 | PASS | Transaction boundaries, durable intent before future external call, post-call result persistence, crash windows, unknown outcome, no blind resubmission, and reconciliation are explicit. |
| 29-38 | PASS | Restart discovery states, duplicate worker safety, process-local-lock insufficiency, durable constraints, single execution authority, and dual legacy/new submission prohibition are explicit. |
| 39-47 | PASS | Broker reference uniqueness, duplicate/conflicting observations, immutable lifecycle history, journaled corrections, history deletion prohibition, durable approvals, and append-only reconciliation are explicit. |
| 48-55 | PASS | Secret/raw-payload exclusion, retention caution, migration, backup, restore, rollback, and outbox deferral are explicit. |
| 56-65 | PASS | Deployment constraints, SQLite limits, PostgreSQL tradeoffs, JSON/in-memory rejection, F5E1 scope, storage spike need, and critical-risk handling are explicit. |

## Durable data model decision

The reviewed model is sufficient for ADR acceptance and future contract design. The accepted durable record inventory is:

- Execution aggregate.
- Execution command.
- Idempotency reservation.
- Lifecycle transition journal entry.
- Broker-reference record.
- Receipt record.
- Failure record.
- Approval record.
- Reconciliation record.

No record is preserved merely because it appeared in F5E0; each record has a distinct safety role. Missing future design details are implementation-level columns, not ADR blockers.

## Transaction-boundary decision

Authoritative local writes for one accepted lifecycle transition must be atomic. No best-effort write can participate in authoritative state. No local transaction may span a broker network call.

Future broker execution sequence remains:

1. Transaction A: validate command, verify expected revision, reserve idempotency, append dispatch-preparation transition, update aggregate to `DISPATCH_PENDING`, persist dispatch intent, commit.
2. External operation: invoke a Paper broker adapter outside the transaction.
3. Transaction B: persist normalized broker result, broker reference if known, accepted lifecycle transition, aggregate snapshot update, or `OUTCOME_UNKNOWN` / `RECONCILIATION_REQUIRED`, then commit.

Crash windows before/during Transaction A are safe local rollback/replay. Windows after Transaction A but before confirmed Transaction B never authorize blind resubmission. Ambiguous external-effect windows require unknown-outcome or reconciliation recovery.

## Idempotency decision

Reservation timing is fixed: authoritative idempotency reservation occurs during command intake / before `IDEMPOTENCY_RESERVED` and before `READY_FOR_DISPATCH`. Dispatch must never occur before the durable reservation exists.

Rules:

- Same command ID plus same payload: exact replay, same logical result, no revision increment, no second broker call.
- Same command ID plus different payload: command conflict, no mutation, no broker call.
- Different command ID plus same idempotency key plus same logical fingerprint: logical replay, original result, no second broker call.
- Same idempotency key plus different logical fingerprint: idempotency conflict, no mutation, no broker call.
- Concurrent identical requests: exactly one reservation succeeds; others observe original or pending result.
- Concurrent conflicting requests: at most one reservation succeeds; others fail deterministically.
- Stuck reservations: recovered by status/lease semantics plus operator or reconciliation path; key reuse is unsafe.

## Optimistic concurrency decision

`PaperExecutionRevision` is a non-negative execution-only revision. Initial revision is zero. Accepted transitions increment exactly once. CAS must compare the exact expected revision. Stale writes change nothing. Transition journal append and aggregate snapshot update are atomic. Terminal states reject mutation unless a bounded reconciliation/failure transition applies. Revision cannot reset or decrement.

Qualification revision and broker status sequence numbers are not execution aggregate revisions.

## Cross-process coordination decision

Future correctness must rely on durable uniqueness constraints, compare-and-swap updates, database transactions, row locks or equivalent claims, and durable idempotency. Process-local mutexes may reduce contention but cannot prove duplicate-prevention for broker execution.

Dual legacy/new broker submission must be prohibited by configuration and architecture tests before broker execution is authorized.

## Restart and recovery decision

Consequential non-terminal states are discoverable on startup. `DISPATCH_PENDING`, `DISPATCHED`, `OUTCOME_UNKNOWN`, `RECONCILIATION_REQUIRED`, `CANCEL_PENDING`, `REPLACE_PENDING`, and `PARTIALLY_FILLED` require read-only broker evidence, reconciliation, or operator visibility before new state-changing commands proceed. Local state alone cannot prove broker success.

## Append-only and event-sourcing decision

Decision: materialized aggregate table plus append-only lifecycle transition journal.

This is not full event sourcing. Full event sourcing remains rejected for the current milestone because the safety properties can be met with a simpler current-state snapshot plus immutable transition history.

## Outbox decision

A transactional outbox is not a broker-call mechanism and is not implemented here. It is required before external event publication becomes authoritative. Direct event publication inside a transaction is unsafe; post-commit best-effort publication may lose notifications; `NullEventPublisher` is not durable. Event-publisher failure must not corrupt authoritative state.

## Storage decision

Final backend selection is deferred. The review authorizes `V41-PQ-001F5E-SPIKE — SQLite/PostgreSQL Execution Durability Comparison`.

SQLite may be selected later only for local single-machine deployment with WAL, foreign keys, explicit migrations, durable backups, restore validation, no network filesystem, and a documented future PostgreSQL path.

PostgreSQL is the stronger default for multi-worker, multi-process, or multi-host deployment, but it carries operational cost that is not justified without the spike evidence.

JSON/JSONL and in-memory stores are rejected as authoritative execution storage. Redis/key-value storage is insufficient by itself for the aggregate/journal transaction model.

## F5E1 readiness

F5E1 as a broad milestone is `READY_WITH_CONDITIONS` because durable database work still requires the spike.

F5E1A — Persistence Contracts and Unit-of-Work Ports: `READY_FOR_IMPLEMENTATION`.

F5E1B — Deterministic In-Memory Reference Adapter: `READY_FOR_IMPLEMENTATION`.

F5E1A/B may define contracts, immutable repository results, typed conflicts, deterministic in-memory reference behavior, and contract tests. They must not implement a durable backend, migrations, runtime wiring, broker integration, or execution authority.

## Findings summary

Critical findings: 0 open.

Major findings: 0 open, 3 closed.

Minor findings: 0 open, 3 closed, 1 deferred.

Observations: 0 open, 5 closed, 5 deferred.

## Acceptance decision

ADR-007 satisfies acceptance requirements:

- source-of-truth hierarchy is explicit;
- durable data model is complete at ADR level;
- transaction boundaries are complete;
- idempotency rules are complete;
- optimistic concurrency rules are complete;
- crash recovery is safe;
- append-only history is clear;
- migration and rollback are safe;
- security exclusions are clear;
- comparative storage spike is explicit;
- F5E1A/F5E1B scope is bounded;
- broker execution remains prohibited;
- no unresolved critical or major risk remains.

## Exact next authorized slice

`V41-PQ-001F5E1A — Persistence Contracts and Unit-of-Work Ports`.

The comparative storage spike is authorized but may proceed only as an isolated, non-production spike. No durable database adapter and no broker execution are authorized by this review.

## Non-implementation statement

This Sentinel review changed documentation only. It did not implement persistence code, persistence ports, repositories, a unit of work, schemas, migrations, durable idempotency, broker ports, broker adapters, runtime wiring, simulator access, event publication, metrics, logging, UI/API/CLI behavior, dependencies, configuration, Live behavior, or execution authority.
