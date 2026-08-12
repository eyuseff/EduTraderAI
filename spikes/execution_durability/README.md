# Execution Durability Storage Spike

This directory contains isolated, non-production technology-spike code for comparing SQLite and PostgreSQL against ADR-007 execution-persistence semantics.

The spike uses synthetic records only. It is not imported by runtime code, does not call brokers, does not read simulator state, and does not implement a production persistence adapter.

Generated databases and machine-readable results belong under `build/spikes/execution_durability/`, which is ignored by Git.
