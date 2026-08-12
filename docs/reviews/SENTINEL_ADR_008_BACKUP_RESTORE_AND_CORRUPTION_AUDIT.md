# Sentinel ADR-008 Backup, Restore, and Corruption Audit

## Audit result

PASS.

Backup, restore, WAL, and corruption responses are explicit and fail-closed.

## Backup decision

Backups must use SQLite backup API or another approved WAL-safe method. Direct copying of a live database file is rejected. Backup destination must be separate, local, permission-restricted, outside the repository, outside `state/`, outside cloud-sync, and outside network shares.

Required metadata: UTC timestamp, application version, schema version, migration checksum summary, source database fingerprint, backup checksum, method, and trigger reason.

## Restore decision

Restore requires maintenance mode, stopped execution authority, damaged database preservation, restore to a new path, checksum validation, schema validation, quick check, integrity check, foreign-key check, execution invariant checks, consequential-state discovery, and operator approval before activation.

Unknown outcomes, idempotency records, execution revisions, broker references, and reconciliation records must be preserved.

## WAL checkpoint decision

Routine checkpoints use `PASSIVE`. `FULL` is maintenance. `RESTART` and `TRUNCATE` require maintenance mode, no active execution writer, validated backup posture, and operator approval. WAL and SHM files must not be manually deleted while active. Filesystem free-space monitoring is a future requirement.

## Corruption severity

Critical: quick-check failure, integrity-check failure, FK inconsistency, migration checksum mismatch, required object missing, WAL configuration mismatch, journal/snapshot mismatch, idempotency binding mismatch, broker-reference ownership conflict.

Response: block authoritative execution, preserve database, no automatic repair, no history rewrite, no idempotency reset, no broker resubmission, operator recovery required.

## Audit conclusion

No backup/restore/corruption finding blocks ADR-008 acceptance. F5E2B may implement check primitives and isolated tests, not backup/restore tooling.
