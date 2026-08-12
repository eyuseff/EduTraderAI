# V41-PQ-001F5E Spike Implementation Report

## 1. Executive summary

The isolated SQLite/PostgreSQL durability comparison spike is complete. SQLite produced executable evidence for all 30 synthetic ADR-007 scenarios. PostgreSQL runtime execution was unavailable and was assessed statically through schema and transaction design.

## 2. Starting baseline

Branch: `feature/edutrader-v4.1`. Starting HEAD: `b33dfe34e0339cba305f26ea648d1407e3640af2`. Baseline expected 1,917 tests, 85 architecture tests, and 86.5% coverage.

## 3. Scope

Isolated spike code, spike tests, backend-neutral scenarios, SQLite executable prototype, PostgreSQL schema/static assessment, reports, design update, and roadmap update.

## 4. Exclusions

No production adapter, production schema, production migration, runtime wiring, broker port, broker adapter, broker call, simulator integration, scanner/supervisor integration, execution authority, credentials, dependency, configuration, UI, API, CLI, or Live behavior.

## 5. Environment inventory

Python 3.14.6; SQLite 3.50.4; no `psql`, `postgres`, `pg_ctl`, Docker, `psycopg`, `psycopg2`, `asyncpg`, or `sqlalchemy` available.

## 6. PostgreSQL execution availability

PostgreSQL runtime execution unavailable. 30 PostgreSQL runtime scenarios were marked `NOT_EXECUTED_ENVIRONMENT_UNAVAILABLE`.

## 7. Isolated package structure

Spike source lives under `spikes/execution_durability/` with `common/`, `sqlite/`, `postgres/`, and `reports/` subpackages. Tests live under `tests/spikes/`.

## 8. Shared scenario catalog

The shared scenario catalog contains 30 scenarios covering accepted ADR-007 semantics.

## 9. Schema comparison

Both prototype schemas include aggregates, commands, idempotency, transitions, broker references, receipts, failures, approvals, reconciliations, and schema migrations.

## 10. SQLite setup

SQLite uses temporary local databases, foreign keys, WAL, busy timeout, and explicit transactions.

## 11. PostgreSQL setup or limitation

PostgreSQL schema and transaction statements were created. Runtime execution was skipped because safe local tooling was unavailable.

## 12. Command replay results

SQLite exact command replay passed. PostgreSQL assessed statically.

## 13. Command conflict results

SQLite unique command ID conflict passed. PostgreSQL assessed statically.

## 14. Idempotency replay results

SQLite logical idempotency replay passed. PostgreSQL assessed statically.

## 15. Idempotency conflict results

SQLite idempotency key conflict passed. PostgreSQL assessed statically.

## 16. CAS results

SQLite compare-and-swap success and stale zero-row update passed. PostgreSQL CAS design is stronger through row locks and row-count validation.

## 17. Transaction rollback results

SQLite injected CHECK/foreign-key failures rolled back staged writes.

## 18. Journal integrity results

SQLite append-only transition identity and journal/snapshot consistency checks passed.

## 19. Broker-reference uniqueness results

SQLite normalized broker-reference uniqueness passed without broker access.

## 20. Restart-discovery results

SQLite close/reopen discovery of DISPATCH_PENDING, OUTCOME_UNKNOWN, and RECONCILIATION_REQUIRED passed.

## 21. Concurrency results

SQLite writer serialization and unique reservation behavior were observed. PostgreSQL concurrency runtime evidence remains a gap.

## 22. Migration results

SQLite additive v2 migration with migration metadata passed.

## 23. Backup/restore results

SQLite backup/restore consistency passed.

## 24. Operational comparison

SQLite has low setup burden and deterministic local testing. PostgreSQL has higher operational burden but stronger multi-worker, multi-host, monitoring, backup, and recovery posture.

## 25. Security review

Synthetic data only. Secret-exclusion scenario passed. No credentials were used.

## 26. Evidence limitations

PostgreSQL runtime behavior was not executed in this environment.

## 27. Scoring model

Scale: 0 unsupported to 4 strong support.

## 28. Comparison matrix

SQLite total: 55. PostgreSQL total: 74.

## 29. Final decision

`SELECT_SQLITE_WITH_MANDATORY_POSTGRESQL_MIGRATION_TRIGGER`.

## 30. Deployment constraints

- single machine
- single application deployment authority
- local filesystem only
- WAL enabled
- foreign keys enabled
- explicit transactions
- busy timeout configured
- no network filesystem
- schema migrations required
- backup and restore procedure required
- CAS and uniqueness checks required
- multi-host deployment prohibited
- mandatory PostgreSQL migration triggers documented

## 31. PostgreSQL migration triggers

- multiple application hosts
- multiple active execution workers
- remote shared database access
- high write concurrency
- public multi-user deployment
- managed web service deployment
- operational requirements exceeding local file backup
- network filesystem use
- availability requirements requiring database failover

## 32. Risks

SQLite must not be used for multi-host, high-concurrency, network filesystem, or public multi-user execution.

## 33. Deferred work

Durable adapter design, production migrations, runtime wiring, recovery services, broker execution authorization, and PostgreSQL runtime spike if deployment constraints exceed SQLite.

## 34. Recommended next slice

`V41-PQ-001F5E2A — SQLITE DURABLE ADAPTER DESIGN`.

## 35. Explicit non-production statement

This spike is not production persistence and does not implement a production database adapter.

## 36. Explicit non-execution statement

This spike executes no broker action and grants no execution authority.
