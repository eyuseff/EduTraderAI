# V41-PQ-001F5E2A SQLite Backup and Restore

## Backup model

Backups must use the SQLite backup API or another explicitly approved WAL-safe method. Simple copying of a live `.db` file without WAL/SHM handling is not approved.

Required backup metadata:

- UTC timestamp;
- application version;
- schema version;
- migration checksum summary;
- source database fingerprint;
- backup file checksum;
- backup method;
- operator or automated trigger reason.

## Backup timing

Backups are required before migrations, before release upgrades that affect execution persistence, before broker-execution enablement, and during manual maintenance checkpoints. Routine backup cadence is deferred.

## Backup location

Backups must be in a separate local directory with least-privilege permissions. They must not be stored in the source tree, Git, `state/`, build directories, temporary spike directories, cloud-synced folders, or network shares.

## Restore model

Restore requires:

1. stop execution authority;
2. enter maintenance mode;
3. preserve current database;
4. restore to a new path;
5. verify backup checksum;
6. verify schema version and migration checksums;
7. run `quick_check`;
8. run `integrity_check`;
9. run `foreign_key_check`;
10. run execution invariant checks;
11. discover consequential states;
12. preserve unknown outcomes;
13. obtain operator approval before replacing active database;
14. record restore audit evidence in a future safe mechanism.

## Restore limitations

Restore tooling is not implemented. Restore does not reset idempotency, rewrite history, or authorize broker resubmission.

## WAL checkpoint policy

Routine checkpoints should use `PASSIVE`. `FULL` is reserved for controlled
maintenance windows. `RESTART` and `TRUNCATE` require maintenance mode, no
active execution writer, validated backup posture, and operator approval.
Manual deletion of WAL or SHM files is prohibited while the database may be
active. Filesystem free-space monitoring is a future operational requirement.
