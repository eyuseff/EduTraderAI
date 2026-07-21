# EduTraderAI v4.0 Operational Validation Log

This file is the human-reviewed ledger for the `v4.0.0-rc1` paper observation
window. Do not record credentials, complete account identifiers, raw broker
payloads, or customer data.

## Release-candidate preparation

| UTC date | Source | Verification | Tests | Combined coverage | Simulator smoke | Missing-credential guard | Notes |
|---|---|---|---:|---:|---|---|---|
| 2026-07-20 | Pre-tag working tree | Pass | 372 | 79.4% | Pending final post-change run | Pass in release configuration tests | Frozen baseline before operational instrumentation |
| 2026-07-21 | Operational-validation working tree | Pass | 387 | 79.9% | Manual deterministic submit and supervised scanner preview/submit passed with controlled fixtures | Alpaca Paper selection failed closed before broker composition | Dashboard/export passed; generated simulator orders were removed from the tracked fixture after verification |
| 2026-07-21 | Post-incident `OV-2026-07-21-002` corrective action | Pass | 390 | 80.0% | Paper Order UI rendered approved quantity 100 and rejected quantity `—`; no submission invoked | Unchanged | Presentation-only correction; RC tag intentionally unchanged |

## Campaign kickoff

The campaign opened with a verification-only preflight. This was not counted as
a paper-trading observation session because no trading workflow was exercised.

| Field | Recorded value |
|---|---|
| UTC start/end | 2026-07-21T03:06:42Z / 2026-07-21T03:06:53Z |
| Verification hash | `ddc765b95d0663991db5aade74acbf09c66e3323` (`v4.0.0-rc1`) |
| Release verification | Pass: 387 tests, 84.2% line, 62.7% branch, 79.9% combined coverage |
| Health-snapshot broker mode | `SIMULATED_PAPER` |
| Scanner mode | `SUPERVISED` |
| Deterministic flags | Preview `True`; submission `True`; scanner `True` |
| Credentials | Alpaca Paper key and secret both absent; credentialed smoke remains pending |
| Sanitized preflight export | Ignored local artifact: `build/validation/v4.0.0-rc1-20260720-230714.json` |
| Exported counters | All zero, as expected before a trading session |
| Broker evidence comparison | Not applicable; no preview, decision, or submission occurred |
| Incidents | None |
| Recommendation | **Continue validation** |

### Kickoff performance comparison

Measurements used the documented 300-iteration deterministic fixture. Median
changes are small and do not indicate a regression.

| Operation | RC baseline median | Kickoff median | Change |
|---|---:|---:|---:|
| TradePlanner | 10.709 µs | 10.916 µs | +1.9% |
| PreviewTradeService | 16.625 µs | 16.833 µs | +1.3% |
| SubmitTradeService | 22.791 µs | 23.250 µs | +2.0% |
| ExecutionSupervisor | 58.105 µs | 57.750 µs | -0.6% |
| Scanner signal-to-decision | 72.166 µs | 72.084 µs | -0.1% |

## Controlled evidence rehearsals

These short deterministic rehearsals validate collection and reconciliation
procedures. They do **not** count toward the five required paper-market sessions.

| UTC start/end | Duration | Broker/scanner | Flags | Verification hash | Previewed/submitted/rejected | Duplicate/cooldown/drift | Broker/instrumentation failures | Export and broker evidence | Observation |
|---|---:|---|---|---|---:|---:|---:|---|---|
| 2026-07-21T03:09:01.063903Z / 2026-07-21T03:09:01.270175Z | 0.206s | Simulator / supervised preview-only | Preview `True`; submission `True`; scanner `True` | `ddc765b95d0663991db5aade74acbf09c66e3323` | 2 / 0 / 0 | 0 / 0 / 0 | 0 / 0 | `build/validation/v4.0.0-rc1-20260720-230901.json`; broker orders 6→6; state SHA-256 `0e9e4eecd283a040e775fc2c41071d0d3b00510a0c22e2c932594ac00a97306a` | Manual preview quantity 100 and one qualified scanner decision; 2 approved plans, 1 scanner signal, 1 scanner decision, 4 event attempts; metrics matched unchanged broker evidence; no incident |

## Observation sessions

Add one row per process session. Export metrics before stopping the process.

| UTC start/end | Elapsed | Mode | Manual previews (A/R) | Manual submissions | Scanner cycles/signals/decisions | Scanner submissions | Drift/replay/duplicate/busy/cooldown | Broker failures | Crashes/incidents | Export path/evidence | Operator |
|---|---:|---|---:|---:|---:|---:|---|---:|---:|---|---|
| 2026-07-21T03:19:22.558Z / 2026-07-21T03:20:42Z | 1m 20s | Local Simulator / supervised; deterministic flags all `True` | 2 / 1 expected from completed UI steps; snapshot unavailable | 1, AAPL 100 verified at broker boundary | Not started | 0 | Not reconciled; process ended before export | 0 observed | No app crash; Low incidents `OV-2026-07-21-001` and `OV-2026-07-21-002` | No export; broker orders 6→7 for intended AAPL order; LOW rejection remained at 7 | Codex, user-authorized |

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

## Session 1 disposition

- Verification hash: `ddc765b95d0663991db5aade74acbf09c66e3323`.
- Manual approved workflow: Passed. The UI previewed 100 AAPL shares with
  $10,000 capital, $250 maximum loss, and 2.00 reward/risk; one 100-share
  simulator order was submitted.
- Rejection workflow: Product behavior passed. LOW at 9/8/11 was rejected with
  the visible explanation `Price is below the $10.00 minimum.` and no order.
- Scanner workflow: Not started because the session controller stopped at the
  rejection evidence discrepancy.
- Metrics reconciliation: Incomplete. Process-local metrics were not exported
  before termination.
- Incidents: `OV-2026-07-21-001`, Low and operations-caused, closed as a
  controller mismatch; `OV-2026-07-21-002`, Low and implementation/presentation
  caused, closed after the authorized presentation-only corrective action.
  Neither affected broker safety, sizing formulas, policy decisions, or
  submitted quantity.
- Post-incident verification: `make verify` passed all 387 tests with 84.2% line,
  62.7% branch, and 79.9% combined coverage.
- Post-incident performance: All five deterministic median latencies remained
  within -0.5% to +1.6% of the RC baseline; no performance regression observed.
- Stable credit: **Does not count** toward the five required paper-market
  sessions. It remains evidence for the manual broker mapping and rejection path.

## Corrective action after Session 1

Incident `OV-2026-07-21-002` was closed on 2026-07-21. Rejected Paper Order
plans now show an em dash under `Approved quantity`; approved plans retain their
existing integer display. The correction is confined to `app.py` and a
presentation adapter. Trading logic, policies, sizing, execution, scanner
behavior, broker behavior, and metrics semantics are unchanged.

Verification evidence:

- 25 affected Paper Order preview/UI wiring tests passed, including three new
  regression checks for rejected rendering, approved rendering, and app wiring.
- Streamlit AppTest rendered approved quantity `100` and rejected quantity `—`
  without exceptions or submission.
- `make verify` passed 390 tests; coverage measured 84.3% line, 62.8% branch,
  and 80.0% combined. All 17 dependency-boundary tests passed.
- Post-fix performance medians were 10.875 µs planner, 16.875 µs preview,
  22.959 µs submit, 58.125 µs supervisor, and 72.230 µs scanner
  signal-to-decision. The largest median change from the RC baseline was +1.6%.
- The `v4.0.0-rc1` tag was not moved. Session 2 was not started automatically.

## Stable-release decisions

| Decision | Status | Owner/date | Rationale or follow-up |
|---|---|---|---|
| Process-local idempotency and locking | Pending | | Accept with operational controls or replace before stable |
| `NullEventPublisher` | Pending | | Accept explicitly or select a tested adapter before stable |
| v4.0 stable readiness | Blocked pending observation | | Session 1 incomplete; five reconciled paper-market sessions, the Alpaca Paper smoke, and both infrastructure dispositions remain required |
