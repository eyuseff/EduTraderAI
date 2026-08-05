# Sentinel ADR-008 Approval Checklist

## Checklist result

PASS.

## Checklist

| Item | Result | Note |
|---|---|---|
| Deployment envelope explicit | PASS | One machine, one process authority, one writer coordinator. |
| One execution authority mandatory | PASS | Process-local locks are non-authoritative. |
| Filesystem restrictions complete | PASS | Local filesystem only; NFS, SMB, cloud-sync, remote shares prohibited. |
| Database path safe | PASS | Outside repo, Git, build, temp, state, simulator state, and cloud/network paths. |
| Symlink behavior defined | PASS | Resolve and fail closed if target violates restrictions. |
| Permissions explicit | PASS | DB/WAL/SHM/backups least-privilege and non-world-readable. |
| PRAGMAs complete | PASS | Foreign keys, WAL, synchronous FULL, busy timeout, explicit transactions. |
| Synchronous mode decided | PASS | FULL for initial safety-first adapter. |
| Busy behavior bounded | PASS | 200 ms proposal, no hidden retry. |
| Transaction mode decided | PASS | BEGIN IMMEDIATE for writes. |
| Table inventory complete | PASS | All F5E1A records mapped. |
| Storage representations exact | PASS | Decimal text, UTC timestamp text. |
| Command immutability safe | PASS | Command rows immutable; outcome field insertion-time only. |
| Idempotency binding safe | PASS | Permanent key/fingerprint binding; no destructive reuse. |
| CAS exact | PASS | Aggregate ID + revision, exactly one row. |
| Transition journal append-only | PASS | Unique aggregate/revision and denial triggers. |
| Broker reference uniqueness safe | PASS | One reference to one aggregate; no silent ownership transfer. |
| Receipts/failures immutable | PASS | Immutable normalized safe facts. |
| Approvals safe | PASS | No auth secrets/session data. |
| Reconciliations append-only | PASS | Prior facts not overwritten. |
| Migration model safe | PASS | IDs/checksums/order/backup/startup validation. |
| Startup fail-closed | PASS | Critical failures block execution. |
| Integrity checks complete | PASS | Quick/integrity/FK/invariant checks separated. |
| Corruption handling safe | PASS | Preserve DB, block execution, no auto repair/resubmit. |
| Backup WAL-safe | PASS | SQLite backup API or approved WAL-safe method. |
| Restore validated | PASS | Maintenance mode and operator activation approval. |
| Encryption status honest | PASS | Deferred. |
| Retention appropriately deferred | PASS | Categories identified; periods deferred. |
| PostgreSQL triggers mandatory | PASS | Multi-host/worker/remote/high-availability triggers explicit. |
| F5E2B scope bounded | PASS | Schema/migration/startup-validation only. |
| Broker execution prohibited | PASS | Broker readiness remains NOT_AUTHORIZED. |
| No unresolved critical risk | PASS | 0 critical and 0 major open. |

## Approval decision

ADR-008 final status: Accepted.

F5E2B readiness: `READY_FOR_IMPLEMENTATION`.

F5E2C readiness: `NOT_YET_AUTHORIZED`.

Broker-execution readiness: `NOT_AUTHORIZED`.
