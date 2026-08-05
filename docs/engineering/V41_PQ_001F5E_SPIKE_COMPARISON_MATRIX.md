# V41-PQ-001F5E Comparison Matrix

Scoring scale: 0 unsupported, 1 major limitation, 2 supported with significant conditions, 3 supported adequately, 4 strong support.

| Criterion | SQLite | PostgreSQL | Evidence basis | Notes |
|---|---:|---:|---|---|
| Contract fidelity | 3 | 4 | SQLite executed; PostgreSQL static | Both can model accepted records; PostgreSQL has stronger typed concurrency primitives. |
| Atomic transactions | 3 | 4 | SQLite executed rollback; PostgreSQL static | SQLite passes local transactions; PostgreSQL is stronger for multi-worker services. |
| Unique constraints | 4 | 4 | SQLite executed; PostgreSQL static | Both support required uniqueness. |
| CAS concurrency | 3 | 4 | SQLite executed two-connection writer serialization | SQLite works under single-machine writer serialization; PostgreSQL supports row-level contention. |
| Idempotency races | 3 | 4 | SQLite executed unique-key race approximation | SQLite adequate locally; PostgreSQL better for concurrent workers. |
| Append-only journal integrity | 4 | 4 | SQLite executed; PostgreSQL static | Primary keys and CHECK constraints model append-only accepted transitions. |
| Restart recovery | 3 | 4 | SQLite reopen executed; PostgreSQL static | SQLite file reopen works locally; PostgreSQL has stronger service restart recovery. |
| Cross-process support | 2 | 4 | Architectural assessment | SQLite has one-writer limits; PostgreSQL designed for multi-process access. |
| Multi-worker support | 1 | 4 | Architectural assessment | SQLite should not be selected for multiple active execution workers. |
| Multi-host support | 0 | 4 | Architectural assessment | SQLite on network filesystems is prohibited; PostgreSQL supports multi-host clients. |
| Migration support | 3 | 4 | SQLite additive migration executed; PostgreSQL static | SQLite migrations are possible but more operationally fragile. |
| Backup/restore | 3 | 4 | SQLite backup executed; PostgreSQL static | SQLite backup API is adequate locally; PostgreSQL has mature dump/PITR options. |
| Local setup simplicity | 4 | 2 | Environment inventory | SQLite is standard library; PostgreSQL tooling unavailable locally. |
| Deterministic testing | 4 | 3 | SQLite executed; PostgreSQL unavailable | SQLite is easier to run hermetically in CI without services. |
| Operational burden | 4 | 2 | Architectural assessment | SQLite has lower local burden; PostgreSQL requires service operations. |
| Portability | 3 | 3 | Architectural assessment | Both portable; SQLite file constraints matter. |
| Future web deployment | 1 | 4 | Architectural assessment | PostgreSQL is the safer web/multi-host target. |
| Security operations | 2 | 4 | Architectural assessment | PostgreSQL has stronger managed controls; SQLite relies on local file controls. |
| Failure observability | 2 | 4 | Architectural assessment | PostgreSQL exposes richer operational monitoring. |
| Upgrade path | 3 | 4 | Architectural assessment | SQLite can start local Paper if migration triggers are explicit; PostgreSQL is the target for scale. |

Totals:

- SQLite: 55
- PostgreSQL: 74

Interpretation: PostgreSQL is architecturally stronger for future multi-worker and web deployment, but SQLite has sufficient executable evidence for initial single-machine local Paper durability under strict constraints.
