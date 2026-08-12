# V41-PQ-001F5E Concurrency Results

## SQLite

Executable evidence was captured with two independent SQLite connections.

Observed behavior:

- `BEGIN IMMEDIATE` serialized writers.
- A second writer attempting to acquire the writer lock while the first held it received lock contention rather than silently updating.
- CAS stale revision behavior produced zero-row updates and was normalized to stale revision rejection.
- Idempotency key races were modeled through uniqueness constraints: one reservation wins; identical replay observes existing state; conflicting logical fingerprint is rejected.

SQLite conclusion: adequate only for single-machine, low-concurrency, one execution authority Paper deployment with explicit transaction discipline and no automatic retry hiding conflicts.

## PostgreSQL

Runtime concurrency was not executed. Static assessment indicates PostgreSQL is stronger for row-level locking, multi-worker CAS conflicts, unique reservation races, isolation levels, and multi-host deployments.
