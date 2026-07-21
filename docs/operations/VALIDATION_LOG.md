# EduTraderAI v4.0 Operational Validation Log

This file is the human-reviewed ledger for the `v4.0.0-rc1` paper observation
window. Do not record credentials, complete account identifiers, raw broker
payloads, or customer data.

## Release-candidate preparation

| UTC date | Source | Verification | Tests | Combined coverage | Simulator smoke | Missing-credential guard | Notes |
|---|---|---|---:|---:|---|---|---|
| 2026-07-20 | Pre-tag working tree | Pass | 372 | 79.4% | Pending final post-change run | Pass in release configuration tests | Frozen baseline before operational instrumentation |
| 2026-07-21 | Operational-validation working tree | Pass | 387 | 79.9% | Manual deterministic submit and supervised scanner preview/submit passed with controlled fixtures | Alpaca Paper selection failed closed before broker composition | Dashboard/export passed; generated simulator orders were removed from the tracked fixture after verification |

## Observation sessions

Add one row per process session. Export metrics before stopping the process.

| UTC start/end | Elapsed | Mode | Manual previews (A/R) | Manual submissions | Scanner cycles/signals/decisions | Scanner submissions | Drift/replay/duplicate/busy/cooldown | Broker failures | Crashes/incidents | Export path/evidence | Operator |
|---|---:|---|---:|---:|---:|---:|---|---:|---:|---|---|
| _pending_ | | | | | | | | | | | |

## Required workflow disposition

| Workflow | Status | Date/evidence | Notes |
|---|---|---|---|
| Simulator manual approved submission | RC smoke passed | 2026-07-21 Streamlit AppTest | 100-share controlled AAPL simulator order; fixture restored afterward |
| Simulator manual policy rejection | RC acceptance passed | `tests/test_v4_release_acceptance.py` | No broker submission |
| Simulator plan-drift rejection | RC acceptance passed | `tests/test_v4_release_acceptance.py`, `tests/test_operational_metrics.py` | Drift counter verified; no broker submission |
| Simulator manual rollback | RC acceptance passed | 2026-07-21 targeted rollback suite | Both manual flags false; legacy engine executed |
| Simulator scanner preview-only | RC smoke passed | 2026-07-21 Streamlit AppTest | Controlled MSFT signal; no broker mutation |
| Simulator scanner controlled submission | RC smoke passed | 2026-07-21 Streamlit AppTest | 100-share controlled MSFT simulator order; fixture restored afterward |
| Simulator scanner replay skip | RC acceptance passed | `tests/test_operational_metrics.py`, supervisor acceptance tests | One broker submission and one replay metric |
| Simulator scanner rollback | RC acceptance passed | 2026-07-21 targeted rollback suite | Legacy brain executed |
| Credentialed Alpaca Paper smoke | Pending | | Must never use a live endpoint |
| Operational dashboard | RC smoke passed | 2026-07-21 Streamlit AppTest | Development mode only; no exceptions |
| Sanitized validation export | RC smoke passed | 2026-07-21 ignored `build/validation/` artifact | Version, flags, health, metrics, and verification metadata; secret scan clean |

## Stable-release decisions

| Decision | Status | Owner/date | Rationale or follow-up |
|---|---|---|---|
| Process-local idempotency and locking | Pending | | Accept with operational controls or replace before stable |
| `NullEventPublisher` | Pending | | Accept explicitly or select a tested adapter before stable |
| v4.0 stable readiness | Blocked pending observation | | All criteria in `VALIDATION_PLAN.md` must pass |
