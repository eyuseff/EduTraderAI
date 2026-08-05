# Sentinel ADR-008 Findings Register

## Review identity

Review: Project Sentinel ADR-008 SQLite Execution Durable Adapter.

Date: 2026-08-05.

Repository branch: `feature/edutrader-v4.1`.

Starting HEAD: `d4f0f3b84b6bcfc6b5cc03d6e3759d225d337485`.

## Findings summary

| Severity | Open | Closed | Summary |
|---|---:|---:|---|
| Critical | 0 | 0 | No critical findings. |
| Major | 0 | 0 | No major findings remain. |
| Minor | 0 | 5 | Minor ambiguities were resolved in ADR-008/F5E2A documentation. |
| Observation | 4 | 0 | Non-blocking deferred operational considerations. |

## Closed minor findings

| ID | Severity | Affected document | Area | Description | Safety consequence | Remediation | Disposition | Verification |
|---|---|---|---|---|---|---|---|---|
| ADR008-MIN-001 | Minor | ADR-008, schema design | Decimal/timestamp representation | Decimal and timestamp storage needed exact canonical format. | Ambiguous serialization could weaken replay/fingerprint consistency. | Canonical decimal `TEXT` and UTC `YYYY-MM-DDTHH:MM:SS.ffffffZ` text recorded; SQLite `REAL` and DB default timestamps rejected. | Closed. | Schema and ADR updated. |
| ADR008-MIN-002 | Minor | Schema design | Command immutability | `processing_outcome` could be misread as mutable. | Mutable command rows could weaken command identity. | Documented as immutable at insertion; later outcomes belong in aggregate, transitions, receipts, failures, or reconciliation. | Closed. | Schema audit. |
| ADR008-MIN-003 | Minor | Schema design | Append-only protections | Trigger scope was incomplete. | History tables could be updated/deleted accidentally. | Denial-trigger model added for commands, transitions, receipts, failures, approvals, reconciliations, and migrations; controlled idempotency/broker-reference updates bounded. | Closed. | Schema audit. |
| ADR008-MIN-004 | Minor | Backup/restore, ADR-008 | WAL checkpoints | Checkpoint modes were deferred too broadly. | Unsafe WAL/SHM handling could corrupt backups or active DB state. | PASSIVE routine default, FULL maintenance use, RESTART/TRUNCATE maintenance-only, no manual WAL/SHM deletion. | Closed. | Backup/corruption audit. |
| ADR008-MIN-005 | Minor | Concurrency, implementation plan | F5E2B scope | F5E2B authorization needed exact boundary. | Implementation could jump to repositories/runtime wiring. | F5E2B limited to schema/migration/connection bootstrap/startup validation/check support/temp-db tests; no repositories or runtime wiring. | Closed. | Approval checklist. |

## Open observations

| ID | Severity | Area | Observation | Disposition |
|---|---|---|---|---|
| ADR008-OBS-001 | Observation | Busy timeout | 200 ms is evidence-backed by spike but should be validated under F5E2B/F5E2D. | Deferred, non-blocking. |
| ADR008-OBS-002 | Observation | Encryption | Database encryption remains deferred and must be revisited before sensitive/support-export expansion. | Deferred, non-blocking. |
| ADR008-OBS-003 | Observation | Retention | Final retention periods require legal/privacy/operational review before commercialization. | Deferred, non-blocking. |
| ADR008-OBS-004 | Observation | PostgreSQL | PostgreSQL remains architecturally stronger for multi-worker/multi-host deployment; runtime evidence remains unavailable locally. | Migration triggers mandatory. |

## Acceptance rule result

Critical open findings: 0.

Major open findings: 0.

Minor findings: closed or explicitly deferred as non-blocking observations.

ADR-008 may move to Accepted.
