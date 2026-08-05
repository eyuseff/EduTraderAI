# Sentinel ADR-007 Storage Decision Audit

## Audit result

PASS WITH SPIKE REQUIRED.

Final backend selection is not justified yet. The review authorizes a comparative storage spike and rejects production durable adapter work until the spike is complete.

## Scored comparison

Score: 1 = weak, 3 = acceptable with constraints, 5 = strong.

| Capability | SQLite | PostgreSQL | JSON/JSONL | In-memory | Redis/KV |
|---|---:|---:|---:|---:|---:|
| Atomic transactions | 4 | 5 | 1 | 1 | 2 |
| Unique constraints | 4 | 5 | 1 | 1 | 2 |
| Optimistic concurrency | 4 | 5 | 1 | 1 | 2 |
| Append-only history | 4 | 5 | 2 | 1 | 2 |
| Restart recovery | 4 | 5 | 2 | 1 | 3 |
| Cross-process coordination | 3 | 5 | 1 | 1 | 3 |
| Local single-user suitability | 5 | 3 | 2 | 2 | 2 |
| Multi-worker suitability | 2 | 5 | 1 | 1 | 3 |
| Multi-host suitability | 1 | 5 | 1 | 1 | 3 |
| Migration support | 3 | 5 | 1 | 1 | 2 |
| Backup/restore | 3 | 5 | 2 | 1 | 2 |
| Operational overhead | 5 | 2 | 4 | 5 | 3 |
| Portability | 5 | 3 | 4 | 5 | 3 |
| Deterministic testing | 5 | 4 | 2 | 5 | 3 |
| Future web deployment | 2 | 5 | 1 | 1 | 3 |

## Decision

Storage position: `AUTHORIZE_COMPARATIVE_SPIKE`.

SQLite is plausible for initial local, single-machine Paper deployment only if WAL, foreign keys, explicit migrations, backups, restore validation, concurrency tests, and no network filesystem are proven.

PostgreSQL is the likely long-term answer for multi-worker or multi-host operation but adds operational overhead that should not be accepted without evidence.

JSON/JSONL is rejected as authoritative execution storage. In-memory storage is restricted to tests and deterministic reference adapters. Redis/KV may support coordination in a future design but is not sufficient by itself as the authoritative aggregate/journal store.

## Authorized spike

`V41-PQ-001F5E-SPIKE — SQLite/PostgreSQL Execution Durability Comparison`.

The spike must compare:

- schema implementation complexity;
- uniqueness constraints;
- compare-and-swap behavior;
- concurrent command races;
- concurrent idempotency reservation;
- transaction rollback;
- restart behavior;
- migration behavior;
- backup/restore;
- multi-process access;
- deterministic tests;
- operational burden.

The spike must not call a broker, wire runtime, mutate production state, select Live behavior, use real credentials, or use `state/simulated_broker.json`.

## Spike acceptance criteria

The spike passes only if it produces:

- isolated prototype schemas for SQLite and/or PostgreSQL;
- reproducible race tests for command and idempotency uniqueness;
- CAS conflict tests;
- rollback and crash-window simulations;
- migration and restore validation notes;
- operational-burden comparison;
- recommendation with explicit deployment constraints;
- no production runtime wiring.

No durable backend adapter is authorized until this evidence is reviewed.
