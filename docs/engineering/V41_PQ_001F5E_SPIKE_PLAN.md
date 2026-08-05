# V41-PQ-001F5E Spike Plan — SQLite / PostgreSQL Execution Durability Comparison

## Purpose

Compare SQLite and PostgreSQL against ADR-007 execution-persistence semantics using isolated synthetic data only.

## Boundaries

The spike is not a production adapter, migration, runtime integration, broker integration, simulator integration, scanner integration, supervisor integration, or execution authorization mechanism.

## Scenario catalog

The shared catalog contains 30 backend-neutral scenarios covering command replay/conflict, idempotency replay/conflict, CAS, rollback, transition journaling, broker-reference uniqueness, restart discovery, concurrency, migration, backup/restore, foreign-key rollback, consistency, and secret exclusion.

## Evidence approach

SQLite is executable with Python standard-library `sqlite3`. PostgreSQL runtime execution is conditional on already-available safe local tooling and driver; absent that, PostgreSQL receives static schema and transaction assessment only.
