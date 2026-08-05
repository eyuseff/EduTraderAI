# Sentinel ADR-007 Findings Register

## Review scope

Review target: `docs/adr/ADR-007-EXECUTION-PERSISTENCE-AND-IDEMPOTENCY.md` and supporting F5E0 persistence architecture documents.

Review date: 2026-08-05.

Starting HEAD: `a6e5cba3c9d927b5a6356d931927d7914199f911`.

## Findings summary

| Severity | Open | Closed | Deferred | Total |
|---|---:|---:|---:|---:|
| Critical | 0 | 0 | 0 | 0 |
| Major | 0 | 3 | 0 | 3 |
| Minor | 0 | 3 | 1 | 4 |
| Observation | 0 | 5 | 5 | 10 |

## Findings

| ID | Severity | Affected document | Affected record or transaction | Description | Safety consequence | Required remediation | Disposition | Verification method |
|---|---|---|---|---|---|---|---|---|
| ADR007-MAJ-001 | Major | ADR-007, transaction boundaries | Dispatch preparation and dispatch result | F5E0 needed Sentinel-level confirmation that no local transaction may span a broker network call and that durable dispatch intent must commit before any future broker call. | A future implementation could create partial authoritative state or repeat a broker operation after crash ambiguity. | Promote the two-transaction external-effect boundary into ADR-007 acceptance text and the review checklist. | Closed | Review confirms Transaction A, external operation, and Transaction B are separate; broker execution remains prohibited. |
| ADR007-MAJ-002 | Major | ADR-007, idempotency model | Command and idempotency reservation | F5E0 needed one authoritative reservation timing rule so implementers do not reserve keys after dispatch or reuse stuck keys unsafely. | Late or ambiguous reservation could permit duplicate broker submission or inconsistent replay. | Define reservation during command intake / before `IDEMPOTENCY_RESERVED` and before `READY_FOR_DISPATCH`; stuck reservations require recovery or operator/reconciliation handling. | Closed | Idempotency audit records replay/conflict behavior, no revision increment on replay/conflict, and no second broker call. |
| ADR007-MAJ-003 | Major | ADR-007, concurrency model | Aggregate transition persistence | F5E0 needed Sentinel-level confirmation that process-local locks are not authoritative for broker execution. | Multi-worker or restarted processes could split-brain and submit duplicate orders. | Require durable uniqueness, transactions, and aggregate revision compare-and-swap as the primary control; process-local locks may only optimize. | Closed | Concurrency and recovery audit records durable constraints, single execution authority, and dual legacy/new submission prohibition. |
| ADR007-MIN-001 | Minor | Durable data model | Retention categories | Retention categories are explicit, but final durations are deferred. | Low risk for implementation sequencing; commercial/legal retention cannot be invented in engineering docs. | Keep legal/regulatory/privacy review as prerequisite before commercialization or deletion policy finalization. | Deferred | Security and retention audit confirms no unsupported retention period is claimed. |
| ADR007-MIN-002 | Minor | Storage assessment | Backend selection | F5E0 did not prove SQLite or PostgreSQL with a runnable technology spike. | Selecting a backend now would be under-evidenced. | Authorize an isolated SQLite/PostgreSQL comparison spike before durable backend implementation. | Closed | Storage decision audit records `AUTHORIZE_COMPARATIVE_SPIKE`; no database adapter is authorized. |
| ADR007-MIN-003 | Minor | Outbox assessment | Event publication | The transactional outbox remains a design decision for external event publication, not broker dispatch. | Future event publication could lose non-authoritative notifications if not addressed. | Defer outbox implementation but require it before event delivery becomes authoritative. | Closed | Outbox audit distinguishes broker calls from outbox events and keeps `NullEventPublisher` non-durable. |
| ADR007-MIN-004 | Minor | Migration plan | Restore validation | Restore validation is specified conceptually but needs implementation-specific checks after backend selection. | Incomplete restore checks could hide revision/journal mismatch. | Carry backend-specific restore validation into F5E-SPIKE and later durable adapter tests. | Closed | Migration and rollback audit lists required restore checks and blocks silent initialization over incompatible stores. |
| ADR007-OBS-001 | Observation | Current implementation | Execution lifecycle core | F5D1 currently provides immutable lifecycle contracts and pure transitions only. | None. | Preserve purity in future persistence ports. | Closed | Implementation inspection of `volcanoes/application/execution/lifecycle`. |
| ADR007-OBS-002 | Observation | Current implementation | Dry-run executor | F5D2 dry-run remains side-effect-free and stops at `WOULD_DISPATCH`. | None. | Do not treat dry-run as operational execution state. | Closed | Implementation inspection of dry-run contracts and executor. |
| ADR007-OBS-003 | Observation | Current implementation | Existing SQLite helpers | Existing SQLite schema includes operational tables but no accepted execution aggregate/idempotency/journal store. | None if not reused as authority. | Future execution persistence must use a dedicated bounded context. | Closed | Inspection of `volcanoes/database` and `volcanoes/portfolio/repository.py`. |
| ADR007-OBS-004 | Observation | Current implementation | Qualification repository | Qualification in-memory repository is deterministic but non-durable and qualification-specific. | None. | Do not reuse it as execution persistence. | Closed | Inspection of `volcanoes/application/qualification/in_memory.py`. |
| ADR007-OBS-005 | Observation | Current implementation | Audit JSONL | `logs/automation_audit.jsonl` is supporting evidence only. | None. | Do not make JSONL authoritative execution storage. | Closed | Inspection of `audit/trade_log.py`. |
| ADR007-OBS-006 | Observation | Future F5E1A | Repository contracts | Port names and method boundaries remain implementation-time details. | Low risk if contract tests are mandatory. | Finalize names only in F5E1A. | Deferred | Implementation plan bounds F5E1A to contracts only. |
| ADR007-OBS-007 | Observation | Future F5E1B | In-memory reference adapter | In-memory reference adapter is useful for deterministic contract tests but not restart-safe. | None if limited to tests and dry architecture validation. | Clearly mark as non-production. | Deferred | Approval checklist limits in-memory storage to tests/reference behavior. |
| ADR007-OBS-008 | Observation | Future F5E-SPIKE | Storage technology | SQLite and PostgreSQL both require empirical concurrency and recovery evidence. | None until selected. | Run isolated spike before backend selection. | Deferred | Storage audit defines acceptance criteria. |
| ADR007-OBS-009 | Observation | Future F5E2/F5E3 | Broker reconciliation | Unknown-outcome reconciliation semantics are accepted, but service implementation remains future work. | None because broker execution is not authorized. | Implement only after durable records exist. | Deferred | Recovery audit keeps blind resubmission prohibited. |
| ADR007-OBS-010 | Observation | Runtime authority | Broker execution | Persistence acceptance does not authorize broker execution. | Prevents accidental scope expansion. | Keep broker execution `NOT_AUTHORIZED`. | Closed | Review outcome and roadmap update. |

## Acceptance rule result

Critical open findings: 0.

Major open findings: 0.

ADR-007 may move to Accepted because all critical and major findings are closed, storage implementation remains blocked pending a spike, F5E1A/F5E1B are bounded to contracts and deterministic in-memory reference behavior, and broker execution remains not authorized.
