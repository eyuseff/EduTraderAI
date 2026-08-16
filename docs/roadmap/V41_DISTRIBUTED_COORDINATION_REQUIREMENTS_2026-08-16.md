# EduTraderAI v4.1 Distributed Coordination Requirements

Date: 2026-08-16

Backlog item: V41-CC-002 — Define distributed coordination requirements.

Status: Requirements defined for technical review; governance approval is not claimed by this document.

Dependency: V41-CC-001 coordination inventory.

## Purpose

Define the invariants that any supported multi-process execution topology must satisfy before a coordination mechanism is selected or runtime behavior is changed. These requirements intentionally build on the existing durable execution command, idempotency, aggregate-CAS, dispatch-control, claim, authorization, resolution, restart-discovery, and reconciliation contracts.

This document does not authorize broker access, Live trading, runtime activation, credentials, or an external order action.

## Architectural premise

The consequential-action authority must be durable and singular. Process-local supervisor registries may remain useful as fast local admission guards, but they must not be the authoritative source of cross-process ownership, idempotency, replay, cooldown, or dispatch permission.

The existing durable execution persistence layer is the baseline authority to preserve unless a later ADR demonstrates that another mechanism is required.

## Required invariants

### DC-REQ-001 — Single consequential owner

For one logical execution identity, at most one worker may hold authority to cross the external effect boundary at a time.

Acceptance evidence:
- competing workers produce one winner and deterministic loser outcomes;
- only the winner receives a dispatch authorization;
- losers cannot invoke the dispatch boundary.

### DC-REQ-002 — Durable idempotency before dispatch

A logical execution must have a durable idempotency reservation before becoming dispatchable. Replays must return deterministic replay/conflict outcomes without creating a second consequential action.

Acceptance evidence:
- exact-command replay;
- logical replay under same idempotency identity;
- identity/payload conflict;
- restart replay after process loss.

### DC-REQ-003 — Revision/CAS protection

All mutable execution aggregate transitions that can affect authority must use expected revision/generation checks. A stale worker must fail closed rather than overwrite newer durable state.

Acceptance evidence:
- stale aggregate revision rejected;
- stale dispatch-control generation rejected;
- racing updates cannot both commit as authoritative.

### DC-REQ-004 — Fenced dispatch authority

Dispatch authority must be bound to a monotonic durable generation and/or equivalent fencing identity so a worker whose authority has been superseded cannot perform a later consequential action.

Acceptance evidence:
- old generation/claim rejected after takeover;
- authorization is cryptographically or structurally bound to the current durable claim identity;
- resolution cannot silently revive superseded authority.

### DC-REQ-005 — Atomic intake-to-dispatch handoff

Command registration, logical idempotency reservation, initial aggregate state and durable dispatch intent must be committed atomically. No partially persisted intake may be discoverable as safe-to-dispatch work.

Acceptance evidence:
- fault injection at every pre-commit write boundary;
- rollback leaves no dispatchable partial state;
- `durable_dispatch_intent` is true only after successful commit.

### DC-REQ-006 — Claim acquisition is durable and exclusive

Worker claim acquisition must be an atomic durable operation. Concurrent claim attempts for the same eligible work must have one deterministic winner or an explicit no-winner failure state.

Acceptance evidence:
- multi-thread/process adversarial claim race;
- exact replay of the winning claim is distinguishable from a new claim;
- identity conflict/already-claimed outcomes are explicit.

### DC-REQ-007 — Authorization follows claim, never precedes it

No dispatch authorization may exist without a valid committed claim, and authorization must bind to the same aggregate, command, idempotency identity, generation and safe order fingerprint as the claim.

Acceptance evidence:
- orphan authorization rejected;
- mismatched authorization rejected;
- reordered write fault injection fails closed.

### DC-REQ-008 — Explicit lease/takeover semantics

If claims may expire or be taken over, the system must define: clock source, expiry duration, renewal policy if any, minimum takeover evidence, monotonic generation change, and behavior under clock skew. If claims do not expire automatically, that non-expiry model must be explicit and recovery must require reconciliation/operator authority as appropriate.

Acceptance evidence:
- boundary-time tests;
- stale claimant cannot dispatch after takeover;
- restart does not erase ownership.

### DC-REQ-009 — Outcome-unknown is terminal for automatic redispatch

Any possible post-effect uncertainty must block automatic retry of the consequential action until reconciliation establishes a safe next state.

Acceptance evidence:
- dispatch exception after possible effect enters `OUTCOME_UNKNOWN`/reconciliation-required semantics;
- restart discovery routes uncertain work to reconciliation, not automatic resubmission;
- duplicate broker references remain fail-closed.

### DC-REQ-010 — Resolution is durable and idempotent

The outcome of a dispatch claim must be durably resolved exactly once by identity, with deterministic exact replay and conflict behavior. A terminal resolution must prevent a second effect for the same authority.

Acceptance evidence:
- duplicate resolution replay;
- conflicting resolution rejected;
- restart observes prior resolution and does not redispatch.

### DC-REQ-011 — Broker-reference ownership is unique

A normalized broker order reference must not become actively owned by two execution aggregates. Ownership conflict must become an explicit uncertain/reconciliation state, never silent reassignment.

Acceptance evidence:
- duplicate reference conflict matrix;
- conflicting owner identity preserved in evidence;
- no automatic second dispatch.

### DC-REQ-012 — Restart recovery is authoritative and bounded

After process restart, recovery must derive work exclusively from durable state using deterministic discovery ordering and filter-bound cursors. Process-local registries must not be required to reconstruct safety.

Acceptance evidence:
- restart with empty process memory reaches the same safe durable decisions;
- pagination/cursor replay is deterministic;
- terminal work is not redispatched.

### DC-REQ-013 — Local supervisor state is advisory only

`ExecutionSupervisor` local active-symbol, in-flight-key, completed-key, duplicate-fingerprint and cooldown registries may reject work earlier, but absence from those registries must never prove that consequential action is safe.

Acceptance evidence:
- a fresh supervisor instance cannot bypass a durable idempotency/claim conflict;
- two supervisor instances share safety through durable authority, not shared Python memory.

### DC-REQ-014 — Symbol-level serialization policy has one durable interpretation

If the product requires one consequential execution per symbol at a time, that rule must be represented by a durable coordination identity or derived from durable active execution state. The same requirement must specify whether independent non-consequential previews may run concurrently.

Acceptance evidence:
- same-symbol competing dispatch attempts;
- different-symbol concurrency remains possible when otherwise safe;
- preview-only behavior remains non-consequential.

### DC-REQ-015 — Cooldown safety must survive restart if authoritative

If cooldown is a safety/control requirement, its reference timestamp must be derived from durable execution history or durable policy state. If cooldown is only a process-local convenience, documentation and UI must not imply cross-restart enforcement.

Acceptance evidence:
- restart during cooldown preserves the required policy outcome when configured authoritative;
- clock boundary tests are deterministic.

### DC-REQ-016 — Fail closed on storage/coordination ambiguity

Failure to read, acquire, authorize, save, commit, verify or reconcile durable authority must not fall back to a process-local allow decision.

Acceptance evidence:
- database busy/timeout/corruption/fault-injection matrix;
- unexpected storage exception produces blocked/unknown state, not dispatch;
- no silent fallback adapter for consequential actions.

### DC-REQ-017 — Transaction boundaries must be explicit

Every operation that relies on atomicity must document which records are committed together and which effect boundary lies outside the transaction. The design must not imply that a database transaction can atomically include an external broker effect.

Acceptance evidence:
- pre-effect versus possible-post-effect failure phases are tested;
- effect boundary invocation occurs only after durable authority grant;
- outcome recording failure after effect becomes uncertainty/reconciliation, not retry.

### DC-REQ-018 — Supported deployment topology must be declared

The release must explicitly state supported combinations of process count, host count and persistence topology. A SQLite-backed deployment must not be described as multi-host safe without evidence for the exact filesystem/storage topology.

Acceptance evidence:
- deployment matrix in release/runbook docs;
- unsupported topologies fail configuration/startup where feasible;
- no implicit distributed-lock claim based solely on SQLite durability.

### DC-REQ-019 — Deterministic safe observability

Every claim, authorization, supersession/takeover, resolution, replay, conflict and reconciliation decision must emit or persist safe correlation identities and reason codes without credentials/account secrets.

Acceptance evidence:
- redaction tests;
- deterministic identity/correlation tests;
- an operator can reconstruct authority history from durable evidence even if external event delivery is unavailable.

### DC-REQ-020 — Recovery authority is singular

Normal dispatch and recovery dispatch must use the same durable ownership/fencing model. Recovery code must not acquire a weaker or parallel authority that can race the normal path.

Acceptance evidence:
- normal worker versus recovery worker race;
- competing recovery workers;
- stale recovery worker after supersession;
- one consequential winner across all paths.

## Required failure-mode matrix

Any selected architecture must explicitly cover at least these failures:

| Failure | Required safe behavior |
|---|---|
| Worker crashes before durable claim | Another eligible worker may later claim; no effect occurred |
| Worker crashes after claim, before authorization | No dispatch; recovery follows defined claim/takeover semantics |
| Worker crashes after authorization, before effect | Recovery proves no effect or follows conservative reconciliation/takeover policy before any new effect |
| Dispatch raises before effect is known | Treat according to proven phase; ambiguous phase becomes outcome-unknown |
| Dispatch may have occurred but acknowledgment is lost | No automatic redispatch; reconciliation required |
| Durable outcome write fails after possible effect | Outcome-unknown/reconciliation; preserve claim/authorization evidence |
| Two workers race for same work | One durable winner; loser blocked/replay/conflict |
| Stale worker resumes after takeover | Fencing rejects consequential action and stale writes |
| Database is unavailable/busy | Fail closed; do not fall back to local allow |
| Corrupt/inconsistent authority rows | Fail closed and route to integrity/reconciliation handling |
| Duplicate broker reference | Preserve conflicting ownership facts; no reassignment or automatic retry |
| Process restarts with empty memory | Safety reconstructed from durable state |

## Non-requirements / out of scope for CC-002

- Selecting Redis, PostgreSQL, a lock service, SQLite topology, or another product.
- Replacing the existing execution persistence contracts.
- Enabling multi-host runtime today.
- Changing broker adapters or endpoints.
- Relaxing Paper-only or consequential-action confirmation boundaries.
- Treating event delivery as the source of execution authority.

## Architecture selection criteria for V41-CC-003

The ADR should prefer the smallest design that satisfies DC-REQ-001 through DC-REQ-020 while preserving existing tested semantics. It must compare at minimum:

1. Extend the existing durable database-backed command/idempotency/CAS/dispatch-claim authority.
2. Add an external coordination service such as Redis leases/locks while retaining database execution records.
3. Move durable authority to a transactional server database if the deployment topology requires multiple hosts.
4. Add an outbox/command-ledger pattern where needed for reliable asynchronous work handoff, without pretending it atomically includes the external broker effect.

Evaluation dimensions: single-source-of-truth risk, fencing strength, crash recovery, operational complexity, deployment topology, testability, migration cost, observability, and fail-closed behavior.

## V41-CC-002 acceptance mapping

- Ownership requirements defined: DC-REQ-001, 006, 007, 020.
- Timeouts/takeover defined as required design decisions: DC-REQ-008.
- Stale locks/workers and fencing defined: DC-REQ-003, 004, 020.
- Recovery/reconciliation defined: DC-REQ-009, 010, 012, 020.
- Failure cases documented: required failure-mode matrix.
- Requirements are ready for technical/governance review; this document does not claim human approval.

The correct next step is V41-CC-003 architecture selection through an ADR proposal, followed by explicit review/acceptance before any coordination implementation.