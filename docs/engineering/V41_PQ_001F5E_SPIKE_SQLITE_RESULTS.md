# V41-PQ-001F5E SQLite Spike Results

SQLite was executed with Python standard-library `sqlite3` and SQLite 3.50.4 using isolated temporary data under `build/spikes/execution_durability/`.

Runtime configuration:

- `PRAGMA foreign_keys = ON`
- WAL journal mode evaluated and enabled where supported
- busy timeout configured
- explicit transactions used
- temporary local database path only
- no production path or simulator state accessed

Results:

- Scenarios executed: 30
- Scenarios passed: 30
- Command replay/conflict: passed
- Idempotency replay/conflict: passed
- CAS success/stale rejection: passed
- Atomic aggregate plus journal transaction: passed
- Rollback after injected failure: passed
- Append-only transition identity: passed
- Broker-reference uniqueness: passed without broker access
- Restart discovery after close/reopen: passed
- Two-connection writer serialization: observed with `BEGIN IMMEDIATE`
- Migration v1 to v2 additive prototype: passed
- Backup/restore validation: passed
- Secret-exclusion validation: passed

SQLite is suitable only under strict local-paper constraints.
