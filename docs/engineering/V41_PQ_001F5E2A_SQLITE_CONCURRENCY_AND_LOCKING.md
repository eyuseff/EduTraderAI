# V41-PQ-001F5E2A SQLite Concurrency and Locking

## Initial supported concurrency

The initial SQLite adapter supports one machine, one application process owning
execution writes, one execution authority, and one active write coordinator.
Multiple local connections are allowed for adapter sessions, backups,
validation, and read-only inspection, but concurrent execution writers are not
approved initially. Multiple local worker processes are prohibited for
authoritative execution writes.

## Durable authority

Correctness depends on:

- SQLite transactions;
- unique constraints;
- exact aggregate revision CAS;
- permanent idempotency bindings;
- broker-reference uniqueness;
- append-only transition identity.

Process-local mutexes may optimize but cannot prove execution safety.

## Lock acquisition

Authoritative writes use `BEGIN IMMEDIATE`. The write reservation is acquired before command, idempotency, and CAS decisions are finalized. This avoids making a local decision that cannot acquire the write lock.

## Busy timeout

Initial proposed busy timeout: 200 ms, based on spike execution. The timeout is bounded and visible. Repeated lock contention must surface as a safe infrastructure outcome and operator-visible diagnostic in a future implementation.

## No hidden retries

The adapter must not hide lock conflicts with unbounded retries. A retry after a possible external effect is especially unsafe and must instead preserve unknown outcome or reconciliation state.

## WAL limitations

WAL improves local read/write behavior but does not make SQLite a multi-host database. WAL files must not be manually deleted or copied while active.

## Multi-process rule

Local multi-process write access is prohibited until a later validation slice proves it under F5E2D or a separate review. Read-only tools may be allowed if they cannot write and respect WAL/backup rules.

Thread model: one process may use multiple threads only through connections
created for the owning thread or through a future explicitly validated
connection policy. Correctness must not rely on Python thread locks.

Process model: maintenance utilities may run only in read-only or maintenance
mode unless a future slice validates a stronger model.

## PostgreSQL trigger

Any need for multiple active execution workers, multi-host operation, remote shared access, or high write concurrency triggers PostgreSQL migration planning before feature expansion.
