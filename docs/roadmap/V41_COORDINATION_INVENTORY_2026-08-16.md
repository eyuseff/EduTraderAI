# EduTraderAI v4.1 Coordination Inventory

Date: 2026-08-16

Baseline: `main` at `907031a53145653e469f3cac6d59aab516261fad`.

Backlog item: V41-CC-001 — Inventory current process-local coordination.

## Purpose

This document inventories the coordination mechanisms currently present in EduTraderAI and separates process-local supervision from durable execution persistence. It does not select a distributed coordination technology and does not change runtime behavior.

No broker credentials, network calls, `state/`, simulator state, Live trading, or external order action were used for this inventory.

## Executive conclusion

EduTraderAI currently has two materially different coordination layers:

1. `ExecutionSupervisor` provides deterministic same-process serialization and policy enforcement using a Python `threading.Lock` plus in-memory registries. Its idempotency replay cache, active-symbol ownership, duplicate fingerprints, and cooldown history are instance/process-local and are not durable across supervisor recreation or process restart.
2. The newer execution application/persistence stack provides storage-neutral durable contracts and a SQLite implementation with command registration, idempotency reservation, revision-checked aggregate saves, append-only transitions, restart discovery, dispatch control/claims/authorization/resolution, unit-of-work atomicity, integrity validation, and reconciliation/recovery support.

The durable layer materially reduces restart and replay risk, but its existence does not make the legacy supervisor's in-memory registries distributed. Multi-process safety must therefore be defined around the durable execution authority, rather than assuming `ExecutionSupervisor` state is shared.

## Coordination inventory

| Mechanism | Primary code path | Current scope / authority | Restart behavior | Existing verification | Risk / implication |
|---|---|---|---|---|---|
| Supervisor state mutex | `volcanoes/application/supervisor/supervisor.py` — `_state_lock = Lock()` and `_admit` / `_finish` critical sections | Serializes access to one `ExecutionSupervisor` instance's registries; thread-safe within one Python process | New process/new supervisor receives a fresh lock | `tests/test_execution_supervisor.py` exercises same-process concurrency | Does not serialize two independent processes or hosts |
| Active-symbol ownership | `ExecutionSupervisor._active_symbols` + `ConcurrentSymbolPolicy` | At most one admitted workflow per symbol in one supervisor instance | Empty after supervisor/process recreation | `test_concurrent_requests_for_same_symbol_never_overlap` | Two independent supervisors can each consider the symbol available unless a durable authority arbitrates |
| In-flight idempotency keys | `ExecutionSupervisor._in_flight_keys` | Rejects a concurrent reuse of the same idempotency key inside one supervisor | Lost on restart | Supervisor idempotency/concurrency tests | Cannot be treated as durable duplicate prevention across processes |
| Completed idempotency replay cache | `ExecutionSupervisor._completed_by_key` | Replays a completed result for the same key and detects key/fingerprint conflicts in one supervisor | Lost on restart | `test_completed_idempotency_key_replays_without_reexecution`; conflict test | Useful local optimization/guard, but durable replay authority belongs in execution persistence |
| In-flight/successful fingerprints | `_in_flight_fingerprints`, `_successful_fingerprints` + `DuplicateExecutionPolicy` | Blocks identical active or previously successful requests known to that supervisor instance | Lost on restart | duplicate-execution supervisor test | Cross-process duplicate prevention cannot depend on these sets |
| Symbol cooldown history | `_last_success_by_symbol` + `CooldownPolicy` | Tracks most recent submitted execution per symbol for one supervisor | Lost on restart | `test_cooldown_blocks_then_allows_distinct_request` | A restart clears local cooldown history unless a future durable policy source supplies it |
| Market-state admission | `MarketStatePolicy` | Deterministic policy gate; optional `require_open`; current policy describes a future authoritative market-state port | Configuration/request fact driven rather than durable ownership | supervisor policy tests | Not a distributed coordination primitive; authoritative market-state sourcing remains separate |
| Command registration | `volcanoes/application/execution/persistence/ports.py` — `ExecutionCommandRepository`; intake service | Storage-neutral durable identity and exact replay/conflict contract | Intended to survive when backed by durable adapter | persistence replay/repository/SQLite suites | Suitable foundation for durable command authority; adapter semantics must remain atomic |
| Idempotency reservation | `ExecutionIdempotencyRepository.reserve`; `TransactionalExecutionIntakeService.intake` | Logical operation reservation inside execution unit of work; returns logical replay/conflict | Durable with SQLite adapter | transactional intake + persistence + SQLite tests | Stronger authority than supervisor-local cache; should be the source for future cross-process duplicate prevention |
| Aggregate CAS/revision checking | `ExecutionAggregateRepository.save(... expected_revision=...)`; intake service | Optimistic concurrency on execution aggregate state | Durable with SQLite adapter | transactional intake, SQLite atomicity/schema/repository tests | Natural primitive for stale-worker rejection; no need to add a second in-memory authority |
| Append-only transition journal | `ExecutionTransitionJournal.append` | Durable accepted lifecycle transition history | Durable with adapter | persistence/SQLite/reconciliation integrity suites | Provides audit/recovery history, not by itself exclusive worker ownership |
| Atomic intake unit-of-work | `TransactionalExecutionIntakeService`; execution unit-of-work provider | Registers command, reserves idempotency, creates/revises aggregate, records approval/transitions, and commits as one transaction | Durable after successful commit | `test_execution_transactional_intake_atomicity.py`, service/restart-discovery tests, SQLite UoW/atomicity tests | Correct boundary for accepted-for-dispatch handoff; partial intake must not leak as dispatchable work |
| Restart discovery | `ExecutionRestartDiscoveryRepository` | Identity-ordered discovery of execution records requiring restart/recovery processing | Explicitly restart-oriented and durable with adapter | restart-discovery tests for in-memory contract and durable execution paths | Recovery workers still require exclusive/fenced dispatch authority when multiple workers compete |
| Dispatch control generation | `ExecutionDispatchControlRepository.save(... expected_generation=...)` | Durable generation-controlled dispatch authority | Durable with adapter | F6B and persistence durability/recovery tests | Provides a fencing/CAS-style primitive; future multi-process design should preserve monotonic authority |
| Dispatch claim | `ExecutionDispatchClaimRepository.acquire` | Durable claim attempt / claim record for dispatch work | Durable with adapter | competing-recovery/stale-worker and persistence tests | Candidate existing primitive for worker ownership; requirements must define expiry/takeover/fencing semantics explicitly |
| Dispatch authorization | `ExecutionDispatchAuthorizationRepository` | Durable authorization tied to claim identity | Durable with adapter | F6B recovery/authorization suites | Consequential execution must remain bound to current valid authority, not local memory |
| Dispatch resolution | `ExecutionDispatchResolutionRepository` | Durable resolution tied to claim identity | Durable with adapter | F6B restart/recovery/integrity suites | Needed to close claims deterministically and avoid ambiguous redispatch |
| Reconciliation persistence | `ExecutionReconciliationRepository` plus application reconciliation layer | Durable brokerless reconciliation facts and recovery history | Durable with adapter | F6B reconciliation integrity, crash fault-injection, restart suites | Handles uncertainty/recovery; does not justify bypassing claim/idempotency controls |
| SQLite execution persistence | `volcanoes/infrastructure/execution_persistence/sqlite/` | Durable local database adapter implementing execution persistence contracts, migrations, integrity, UoW and reconciliation support | Persists across application restart on the same configured durable database | extensive SQLite foundation/repository/schema/atomicity/UoW suites | Durable does not automatically mean horizontally distributed; deployment/storage topology determines cross-process/host behavior |
| In-memory execution persistence adapter | `volcanoes/application/execution/persistence/in_memory/` | Contract-compatible test/local adapter | Process memory only | in-memory atomicity, concurrency, replay, determinism and restart-discovery contract tests | Must not be interpreted as production distributed authority |
| Event publisher default | `ExecutionSupervisor` defaults to `NullEventPublisher` when none is supplied | Observability behavior, not coordination authority | Events may be intentionally discarded | operational event/metrics tests | Coordination decisions must not depend on event delivery; detailed inventory belongs to V41-EP-001 |

## Process-local state lifecycle

The legacy supervisor admission path evaluates all local registries while holding `_state_lock`. On successful admission it records the symbol, idempotency key and request fingerprint as in-flight. `_finish` removes those in-flight entries and, for a completed result, records the result by key; a submitted result additionally records the successful fingerprint and last successful timestamp by symbol.

Those structures are normal Python sets/dictionaries owned by the supervisor instance. There is no constructor rehydration of those registries from the durable execution persistence layer in the reviewed code. Therefore their guarantees are intentionally classified as process-local.

## Durable intake lifecycle

`TransactionalExecutionIntakeService` opens an execution unit of work and performs command registration, logical idempotency reservation, initial aggregate creation, approval/transition persistence, and revision-checked aggregate updates. Exact replay, logical replay, command conflict, idempotency conflict, and stale revision cause rollback/fail-closed outcomes. `durable_dispatch_intent` becomes true only after a successful commit.

This is a materially stronger coordination boundary than the supervisor-local dictionaries because it is storage-neutral and can be backed by the SQLite adapter. It should be treated as the existing foundation for V41-CC-002 requirements and V41-CC-003 architecture selection.

## Risk map

### R1 — Multiple supervisor instances

Two `ExecutionSupervisor` instances do not share `_active_symbols`, in-flight keys, fingerprints, completed results, or cooldown history. A multi-process deployment must not claim cross-process exclusion from those fields.

### R2 — Restart resets legacy admission memory

Supervisor replay, duplicate and cooldown memory is rebuilt empty when a new instance is created. Durable execution records can survive, but the two layers must not be conflated.

### R3 — Dual-authority drift

If future runtime paths independently enforce consequential ownership in both local supervisor state and durable dispatch state, disagreements can create either duplicate action risk or unnecessary blocking. The durable execution authority should have one clearly documented precedence model.

### R4 — Stale worker / competing recovery

The repository already contains dispatch generation, claim, authorization and resolution contracts plus stale-worker/competing-recovery tests. V41-CC-002 should formalize fencing, takeover, timeout and terminal-resolution invariants around these existing primitives rather than inventing a parallel lock system.

### R5 — SQLite topology assumptions

SQLite persistence is durable for the configured database, but durability alone does not establish safe multi-host locking semantics. Any deployment beyond a single shared-storage/process topology requires explicit supported-topology requirements and adversarial validation.

### R6 — Cooldown authority after restart

If cooldown is a safety requirement rather than a convenience policy, its authoritative timestamp must be derived from durable execution history or another durable policy state. The current `_last_success_by_symbol` is local only.

## V41-CC-001 acceptance mapping

- Locks inventoried: `ExecutionSupervisor._state_lock` and its critical sections are documented.
- Registries inventoried: active symbols, in-flight keys/fingerprints, successful fingerprints, completed results and last-success timestamps are documented.
- Idempotency inventoried: local replay/conflict cache is separated from durable command/idempotency repositories.
- Cooldowns inventoried: local timestamp state and restart limitation are documented.
- Symbol serialization inventoried: same-process `ConcurrentSymbolPolicy` semantics and limitation are documented.
- Restart behavior inventoried: local state loss is distinguished from durable SQLite execution/recovery state.
- Risks mapped to code paths: R1–R6 map the current mechanisms to multi-process/restart implications.

## Recommended handoff to V41-CC-002

Define requirements before selecting Redis, database locks, leases, or another coordination product. The requirements should start from the repository's existing durable command/idempotency/CAS/dispatch-claim model and specify: single consequential owner, fencing, stale-worker rejection, takeover/expiry, idempotent replay, atomic handoff, restart recovery, terminal resolution, supported deployment topology, observability, and fail-closed behavior.

No coordination implementation is authorized or implied by this inventory.