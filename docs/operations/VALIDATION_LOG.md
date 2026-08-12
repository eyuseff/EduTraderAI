# EduTraderAI v4.0 Operational Validation Log

This file is the human-reviewed ledger for the `v4.0.0-rc1` paper observation
window. Do not record credentials, complete account identifiers, raw broker
payloads, or customer data.

Supporting campaign records:

- `VALIDATION_PLAN.md` defines acceptance criteria and metric semantics.
- `RC_RUNBOOK.md` defines the authorized session procedure.
- `EVIDENCE_MANIFEST.md` records retained local evidence hashes.
- `WEEKLY_REVIEW_TEMPLATE.md` defines the required week-end review fields.
- `WEEKLY_REVIEW_WEEK_01.md` is the populated interim Week 1 review.
- `ALPACA_PAPER_SMOKE_CHECKLIST.md` defines the separately authorized,
  credential-safe paper-broker procedure.
- `CI_PUSH_READINESS.md` records workflow, dependency, artifact, and push-gate
  risks without changing release tooling.
- `INCIDENT_TEMPLATE.md` defines incident evidence and disposition fields.

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
| 2026-07-21T03:39:59.918985Z / 2026-07-21T03:40:03.867174Z | 3.948s | Isolated Local Simulator / supervised preview-only scanner; deterministic flags all `True`; legacy rollback flags inactive | 2 / 1 service invocations: one visible approved preview, one required fresh pre-submit recomputation, one visible rejection | 1, AAPL 100 | 1 / 0 / 0; normal MSFT scan produced no qualifying signal | 0 | 0 / 0 / 0 / 0 / 0; idempotency conflicts also 0 | 0 | No crash or incident; expected bare-mode Streamlit context warning only | `build/validation/session2-final-20260721T033959Z.json` SHA-256 `44d5cf603f7373be8ba279fc1d3bd1df87d83115f84398e6723d1f636620223d`; observer evidence `build/validation/session2-observer-20260721T033959Z.json`; isolated broker orders 0→1 | Codex, user-authorized |
| 2026-07-21T15:46:21.373648Z / 2026-07-21T15:46:22.763301Z | 1.390s | Isolated Local Simulator / supervised controlled submission; deterministic flags all `True`; legacy rollback flags inactive | 2 / 1 service invocations: visible AAPL approval, fresh pre-submit recomputation, visible LOW rejection | 1, AAPL 100 | 1 / 1 / 1; controlled MSFT signal traversed the supervisor | 1, MSFT 100 | 0 / 0 / 0 / 0 / 0; idempotency conflicts also 0 | 0 | No crash or incident; expected bare-mode Streamlit context warning only | `build/validation/session3-final-20260721T154621Z.json` SHA-256 `89700b3e04e6e3819dbeb0ae68a4bfb6f5297841eaddb4ccf228c774ad71c9cc`; observer `build/validation/session3-observer-20260721T154621Z.json`; isolated broker orders 0→2 | Codex, user-authorized |
| 2026-07-21T16:06:35.798771Z / 2026-07-21T16:06:37.184892Z | 1.386s | Isolated Local Simulator / supervised controlled submission; deterministic flags all `True`; legacy rollback flags inactive | 3 / 2 UI-driven service invocations: default render, configured NVDA approval, fresh pre-submit recomputation, post-submit duplicate-order rejection, intentional BADRR rejection | 1, NVDA 125 | 1 / 1 / 1; controlled AMZN signal traversed the supervisor | 1, AMZN 62 | 0 / 0 / 0 / 0 / 0; idempotency conflicts also 0 | 0 | No app crash; Low operations/evidence-harness incident `OV-2026-07-21-003` closed by direct reconciliation | `build/validation/session4-final-20260721T160635Z.json` SHA-256 `cf3ee66d4c4ca73cf0e770f36e4ca000b5d6d5b8e5182c99ea7aa4c57d5120fd`; observer `build/validation/session4-observer-20260721T160635Z.json`; isolated broker orders 0→2 | Codex, user-authorized |
| 2026-07-22T12:28:38.325213Z / 2026-07-22T12:28:38.571632Z | 0.246s | Isolated Local Simulator / deterministic flags all `True`; stopped before scanner | Default approved render, configured TSLA approval, fresh pre-submit recomputation, then OVERCAP remained approved after deterministic cap to 40 rather than producing the required rejection | 1, TSLA 62 | Not started | 0 | Not exported after the failed rejection gate | 0 observed | No app crash; Low operations/scenario-selection incident `OV-2026-07-22-004` closed by disposition; session invalid | Initial snapshot, failure record, pre-verification metadata, and partial isolated broker state listed in `EVIDENCE_MANIFEST.md`; no final export | Codex, user-authorized |
| 2026-07-22T20:11:56.617202Z / 2026-07-22T20:11:57.659760Z | 1.043s | Isolated Local Simulator / supervised controlled submission; deterministic flags all `True`; legacy rollback flags inactive | 3 / 1 UI-driven service invocations: default AAPL approval, configured AMD approval, fresh AMD pre-submit recomputation, and intentional BADRR7 hard rejection | 1, AMD 125 | 1 / 1 / 1; controlled CRM signal traversed the supervisor | 1, CRM 62 | 0 / 0 / 0 / 0 / 0; idempotency conflicts also 0 | 0 | No crash or incident; expected bare-mode Streamlit warning only | `build/validation/session7-final-20260722T201156Z.json` SHA-256 `f6875e2d3e98255d64014323313b33301d903f67a1a0c7a346a48530ae13e35a`; observer `build/validation/session7-observer-20260722T201156Z.json`; isolated broker orders 0→2 | Codex, user-authorized |
| 2026-07-23T13:03:44.379633Z / 2026-07-23T13:03:44.707997Z | 0.328s | Isolated Local Simulator / supervised controlled submission; deterministic flags all `True`; legacy rollback flags inactive | 3 / 1 UI-driven service invocations: default AAPL approval, configured MSFT approval, fresh MSFT pre-submit recomputation, and intentional BADRR8 hard rejection | 1, MSFT 125 | 1 / 1 / 1; controlled ORCL signal traversed the supervisor | 1, ORCL 62 | 0 / 0 / 0 / 0 / 0; idempotency conflicts also 0 | 0 | No crash or incident; expected bare-mode Streamlit warning and one pre-app temporary-controller import-path warning only | `build/validation/session8-final-20260723T125022Z.json` SHA-256 `9c091c1c1ae0138ba1d824cf540a76719b93a4e5823c661d2ed0366ad4619cc1`; observer `build/validation/session8-observer-20260723T125022Z.json`; isolated broker orders 0→2 | Codex, user-authorized |

## Required workflow disposition

| Workflow | Status | Date/evidence | Notes |
|---|---|---|---|
| Simulator manual approved submission | Operational observation passed | Sessions 2, 3, 4, 7, and 8 | Session 8 submitted MSFT 125; preview, planner, pipeline, and isolated broker evidence reconciled exactly |
| Simulator manual policy rejection | Operational observation passed | Sessions 2, 3, 4, 7, and 8 | Session 8 BADRR8 reward/risk rejection showed `Approved quantity: —` and created no order |
| Simulator plan-drift rejection | RC acceptance passed | `tests/test_v4_release_acceptance.py`, `tests/test_operational_metrics.py` | Drift counter verified; no broker submission |
| Simulator manual rollback | RC acceptance passed | 2026-07-21 targeted rollback suite | Both manual flags false; legacy engine executed |
| Simulator scanner preview-only | Operational no-signal cycle passed | Session 2, 2026-07-21 | Normal MSFT scan in Bullish regime scored 75; no signal qualified, no supervisor decision, and no broker mutation |
| Simulator scanner controlled submission | Operational observation passed | Sessions 3, 4, 7, and 8 | Controlled ORCL 62 in Session 8 traversed supervisor, shared planner, pipeline, and Local Simulator adapter |
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

## Session 2 disposition

- Exact tested commit: `6a1cf97b9027ceb92242a032bca9b4bb802ff662`;
  release-candidate tag `v4.0.0-rc1` remained at
  `ddc765b95d0663991db5aade74acbf09c66e3323`.
- Configuration: isolated Local Simulator state, supervised deterministic
  scanner, all three deterministic flags enabled, legacy rollback paths inactive,
  no Alpaca credentials, and no external broker calls. Initial health reported
  `SIMULATED_PAPER`, `SUPERVISED`, `NullEventPublisher`, and process-local
  supervisor state. Initial counters were all zero.
- Manual approved workflow: AAPL at 100/97.5/105 displayed quantity 100,
  $10,000 capital, $250 maximum loss, and 2.00 reward/risk. Submission performed
  the required fresh deterministic recomputation and created exactly one accepted
  100-share Local Simulator bracket order.
- Manual rejection workflow: LOW at 9/8/11 displayed
  `Price is below the $10.00 minimum.`, showed `Approved quantity: —`, and left
  the isolated broker order count unchanged at one.
- Scanner workflow: one normal MSFT scan completed against current market data.
  The regime was Bullish with score 75, no signal qualified, the UI reported no
  candidates and no paper previews/orders, and the supervisor correctly received
  zero execution requests. This is valid no-signal evidence, not a failure.
- Authoritative counters: previews 3, approved plans 2, rejected plans 1,
  submissions 1, scanner signals 0, scanner decisions 0, event-publication
  attempts 6. The three previews are the visible approved preview, required fresh
  pre-submit recomputation, and visible rejected preview.
- Safety counters: broker failures, plan drift, idempotent replays, idempotency
  conflicts, duplicate executions, symbol-busy rejections, cooldown rejections,
  and instrumentation failures were all zero.
- Reconciliation: previews equalled approved plus rejected plans; submission and
  broker-order deltas both equalled one; the broker quantity equalled the approved
  deterministic quantity; rejection and scanner steps added no orders; every
  latency observation count matched its operation counter; and six publication
  attempts matched six publication-latency observations. No discrepancy remained.
- Correlation/idempotency: the fresh preview and submission shared the lifecycle
  within the submission rerun, and no replay or conflict was observed. The null
  publisher intentionally retains no correlation-bearing payloads, so the export
  proves publication attempt consistency rather than durable event reconstruction;
  this remains a documented platform limitation, not a Session 2 incident.
- Preserved exports: authoritative final snapshot
  `build/validation/session2-final-20260721T033959Z.json` and supplementary
  reconciler evidence `build/validation/session2-observer-20260721T033959Z.json`.
  The initial snapshot is
  `build/validation/session2-initial-20260721T033959Z.json`.
- Isolation: Session 2 temporary broker state was removed after evidence capture.
  Session 1's tracked simulator evidence remained unchanged at SHA-256
  `669ed4abfe0ff1b50b54ca1011eef0aba214a5e04bd41c4a0764bda60657811c`.
- Verification: both pre-session and post-session `make verify` runs passed 390
  tests with 84.3% line, 62.8% branch, and 80.0% combined coverage.
- Incidents: none. The expected Streamlit AppTest bare-mode `ScriptRunContext`
  warning had no application, evidence, or trading effect.
- Stable credit: **Counts as validation session 1 of 5**. Session 1 remains a
  historical incomplete record and does not receive stable credit.

## Session 3 disposition

- Exact tested commit: `6a1cf97b9027ceb92242a032bca9b4bb802ff662`;
  `v4.0.0-rc1` remained at
  `ddc765b95d0663991db5aade74acbf09c66e3323`.
- Configuration: fresh isolated Local Simulator state, supervised deterministic
  scanner, all deterministic flags enabled, legacy rollback paths inactive, no
  Alpaca credentials, and no external market or broker calls. Initial health
  reported `SIMULATED_PAPER`, `SUPERVISED`, `NullEventPublisher`, process-local
  supervisor state, and zero counters.
- Manual approved workflow: AAPL at 100/97.5/105 displayed quantity 100,
  $10,000 capital, $250 maximum loss, 2.00 reward/risk, and an approved policy
  outcome. The submission rerun recomputed the plan and created one accepted
  100-share bracket-limit simulator order with unique order ID
  `40d6774c-f774-4a3c-8007-8600979d50c4`.
- Manual rejection workflow: LOW at 9/8/11 displayed
  `Price is below the $10.00 minimum.`, `Approved quantity: —`, and no broker
  order delta.
- Scanner workflow: a controlled MSFT simulator signal scored 95 in a controlled
  Bullish regime and traversed `SupervisedEduTraderBrain`,
  `ExecutionSupervisor`, the shared preview/submission planner, execution
  pipeline, and Local Simulator adapter. It created exactly one accepted
  100-share MSFT bracket-limit order with unique order ID
  `0a94d039-6e37-4a0a-96f9-5648cb68d6e2`. Its deterministic idempotency key was
  `scanner-5cc9604a4cf1ed1ce3ab6faa16a0b411b1172b77229a4edad277cc228ab26f6b`.
- Authoritative counters: previews 4, approved plans 3, rejected plans 1,
  submissions 2, scanner signals 1, scanner decisions 1, and event-publication
  attempts 10. Preview, submission, supervisor, scanner-decision, and publication
  latency counts exactly matched their operation counters.
- Reconciliation: the four previews partitioned into three approvals and one
  rejection; two submissions equalled two unique broker orders; manual and
  scanner quantities, symbols, sides, prices, stops, targets, and bracket-limit
  order types matched their deterministic plans. The rejected plan created no
  order. Plan drift, replay, idempotency conflict, duplicate execution,
  symbol-busy, cooldown, broker failure, and instrumentation failure counters
  were all zero.
- Event evidence: ten publication attempts matched ten publication-latency
  observations and the expected service/supervisor sequence count. The configured
  null publisher intentionally retains no correlation-bearing payloads; release
  tests verify propagation and order. This is the accepted paper limitation from
  ADR-0009, not an incident or fabricated operational correlation record.
- Evidence: initial, final, observer, isolated broker state, scanner audit, and
  pre/post verification metadata are listed in `EVIDENCE_MANIFEST.md`. The final
  export SHA-256 is
  `89700b3e04e6e3819dbeb0ae68a4bfb6f5297841eaddb4ccf228c774ad71c9cc`;
  observer SHA-256 is
  `11abb6137638a374a96e4b1cda582cf8d47c72cdef303afce8bafacdd3bdb506`.
- Isolation and integrity: temporary Session 3 simulator state was removed only
  after preserved copies were written. Session 1, Session 2, kickoff, rehearsal,
  and scanner-audit hashes remained unchanged. Rolling `build/verification.json`
  and `build/coverage.json` changed only through the mandatory release gate, with
  named Session 3 verification metadata preserved.
- Verification: pre- and post-session `make verify` each passed 390 tests with
  84.3% line, 62.8% branch, and 80.0% combined coverage. Black, Ruff, MyPy,
  17 architecture tests, imports, and Streamlit compilation passed. The release
  gate does not include the separate performance benchmark, so none was run.
- Incidents: none. The expected AppTest bare-mode `ScriptRunContext` warning had
  no trading, application, evidence, or reconciliation effect.
- Stable credit: **Counts as validation session 2 of 5**. The campaign still must
  reach five valid sessions spanning at least seven calendar days before stable.

## Stable-readiness checkpoint after Session 3

This checkpoint distinguishes operational observation from controlled test
evidence. A green release suite does not replace the remaining observation
window, credentialed paper-broker smoke, or explicit infrastructure decisions.

| Acceptance criterion | Current status | Authoritative evidence | Remaining requirement |
|---|---|---|---|
| Incorrect submitted quantities: 0 | Observed pass | Sessions 2 and 3; Session 3 AAPL and MSFT plans and orders all quantity 100 | Continue reconciling every later submission |
| Silent material plan drift: 0 | Test-backed and observed zero | Release drift tests; Sessions 2 and 3 `plan_drift=0` | Preserve zero tolerance; exercise drift only with controlled fixtures |
| Unintended duplicate broker submissions: 0 | Observed zero; test-backed replay protection | Session 3 two submissions equalled two unique broker orders; replay tests passed | Continue comparing orders, submissions, replay, and duplicate counters |
| Correlation-ID loss: 0 | Test-backed; durable operational evidence unavailable | Event reconstruction tests; Session 3 ten publication attempts matched ten timing observations | Retain ADR-0009 constraint; null publication cannot preserve payloads |
| Unresolved symbol-lock leaks: 0 | Test-backed; one supervised request completed operationally | Session 3 MSFT request completed without busy/deadlock outcome; concurrency tests passed | Continue observing later supervised requests |
| Supervisor deadlocks: 0 | Observed pass | Session 3 supervised MSFT execution completed in-session; supervisor tests passed | Maintain operator timeout |
| Unexplained application crashes: 0 | Observed pass | Sessions 2 and 3 clean stops; Session 1 incidents explained and closed | Maintain zero unexplained crashes |
| Simulator manual workflow | Operational approved/rejection observations pass | Sessions 2 and 3 approved submit and policy rejection; controlled drift and rollback tests | Preserve evidence and repeat normal sessions as scheduled |
| Simulator scanner workflow | Operational preview-only and controlled submission observations pass | Session 2 no-signal cycle; Session 3 controlled supervised submission; replay and rollback tests | Continue normal observation without an arbitrary trade quota |
| Credentialed Alpaca Paper smoke | Pending | Missing-credential guard passes safely | Requires operator-managed Alpaca Paper credentials and explicit session authorization |
| Rollback behavior | Controlled tests pass | Manual and scanner rollback acceptance/configuration tests | Keep flags inactive during deterministic sessions; verify again when the campaign schedules rollback observation |
| Process-local coordination disposition | Proposed accept with constraints | ADR-0008 documents instance scope, restart/multi-process failure modes, and single-process paper controls | Approve the constraints at stable review and demonstrate continued compliance; durable coordination remains required for expansion |
| `NullEventPublisher` disposition | Proposed accept with constraints | ADR-0009 documents retained evidence, audit/recovery gaps, and mandatory broker reconciliation | Approve the constraints at stable review; durable publication remains required for live, distributed, unattended, or recovery-dependent use |
| Observation window | 2 of 5 valid sessions | Sessions 2 and 3 are fully reconciled | Three more sessions and a total span of at least seven calendar days |
| Release verification | Pass | Pre- and post-Session 3 `make verify`: 390 tests, 80.0% combined coverage | Re-run before and after every later session |
| Incident status | Pass | Session 1 Low incidents closed; no Session 2 or Session 3 incident | No critical or unresolved high incidents at stable decision |

## Session 4 disposition

- Exact tested commit: `6a1cf97b9027ceb92242a032bca9b4bb802ff662`;
  `v4.0.0-rc1` remained at
  `ddc765b95d0663991db5aade74acbf09c66e3323`.
- Configuration: fresh isolated Local Simulator state, supervised deterministic
  scanner, all deterministic flags enabled, all legacy rollback paths inactive,
  no Alpaca credentials, and no external market or broker calls. Initial health
  and counters were clean and zero.
- Manual approved workflow: NVDA at 50/48/54 displayed and submitted quantity
  125, $6,250 capital, $250 maximum loss, and 2.00 reward/risk. The fresh
  pre-submit recomputation matched symbol, side, quantity, prices, order type,
  sizing, and approved policy outcome. The Local Simulator accepted one bracket
  order with ID `24e2f216-67e8-44e8-8891-a3fb2f25f119`.
- Manual rejection workflow: BADRR at 50/48/53 displayed
  `Reward/risk 1.50 is below the required 2.00.`, showed
  `Approved quantity: —`, and created no order.
- Scanner workflow: a controlled AMZN signal scored 96 in a controlled Bullish
  regime and traversed scanner, `ExecutionSupervisor`, the shared preview and
  submission services, `TradePlanner`, `ExecutionPipeline`, and Local Simulator
  adapter. It created one accepted 62-share bracket order with ID
  `4a7b3013-c08a-457d-a440-2ce20baad7f2` and deterministic idempotency key
  `scanner-4463656f6e9f8aee1872508cf1040b53040f8ff977cb9ed9c5d06a47f47fe887`.
- Authoritative counters: six previews, four approved plans, two rejected
  plans, two submissions, one scanner signal, one scanner decision, and 14
  event-publication attempts. The additional UI previews are fully accounted
  for by the initial default render and the post-submit rerender, which correctly
  rejected the already-open NVDA order. Four approvals plus two rejections equal
  six previews; 14 event attempts equal 14 publication latency observations.
- Reconciliation: two submissions equal two unique broker orders. Manual and
  scanner symbols, sides, quantities, entry, stop, target, and order types match
  their deterministic plans. Duplicate execution, drift, replay, idempotency
  conflict, symbol-busy, cooldown, broker failure, and instrumentation failure
  counters are all zero. Scanner audit contains exactly `scan_completed` then
  `paper_order_submitted` for AMZN 62.
- Incident `OV-2026-07-21-003`: Low, operations/evidence-harness only, closed by
  direct reconciliation. The external observer initially expected obsolete
  metric names and four previews and stopped after the workflows and exports had
  completed. The original failure record is retained; the authoritative export,
  broker state, scanner audit, and corrected observer evidence agree. No trading,
  application, presentation, or release behavior changed.
- Evidence: all Session 4 artifacts and SHA-256 values are listed in
  `EVIDENCE_MANIFEST.md`. Prior retained evidence remained unchanged: 18 of 18
  manifest entries matched before and after the operational run.
- Verification: pre- and post-session `make verify` each passed 390 tests with
  84.3% line, 62.8% branch, and 80.0% combined coverage. Black, Ruff, MyPy,
  17 architecture tests, imports, and Streamlit compilation passed. The release
  gate does not include the separate performance benchmark, so none was run.
- Stable credit: **Counts as validation session 3 of 5**. Stable remains blocked
  until five valid sessions span at least seven calendar days and the remaining
  release criteria are complete.

## Stable-readiness checkpoint after Session 4

| Acceptance criterion | Current status | Authoritative evidence | Remaining requirement |
|---|---|---|---|
| Incorrect submitted quantities: 0 | Observed pass | Session 4 NVDA 125 and AMZN 62 plans matched broker orders | Continue reconciling every later submission |
| Silent material plan drift: 0 | Test-backed and observed zero | Release drift tests; Session 4 `plan_drift=0` | Preserve zero tolerance |
| Unintended duplicate broker submissions: 0 | Observed pass | Two submissions equalled two unique broker orders | Continue order-to-submission reconciliation |
| Supervisor and idempotency safety | Observed pass and test-backed | AMZN completed without replay, conflict, busy, cooldown, or deadlock outcome | Continue under ADR-0008 deployment constraints |
| Event and correlation evidence | Test-backed; durable payloads unavailable | Fourteen attempts matched fourteen latency observations; ADR-0009 applies | Durable operational reconstruction remains unavailable |
| Observation window | 3 of 5 valid sessions | Sessions 2, 3, and 4 are fully reconciled | Two more valid sessions and at least seven calendar days total span |
| Credentialed Alpaca Paper smoke | Pending | Credential guard and checklist prepared | Requires separate explicit authorization and operator-managed credentials |
| Incident status | Pass | `OV-2026-07-21-003` Low and closed; no unresolved High or Critical incident | Maintain incident discipline |

## Session 5 disposition — invalid attempt

- Exact tested commit: `6a1cf97b9027ceb92242a032bca9b4bb802ff662`;
  `v4.0.0-rc1` remained at
  `ddc765b95d0663991db5aade74acbf09c66e3323`.
- Repository and evidence gates passed before execution. The branch and release
  identity matched, no production Python change was present, all 26 retained
  manifest entries matched SHA-256, and all 23 retained JSON evidence files
  parsed.
- Pre-session `make verify` passed Black, Ruff, MyPy, 17 architecture tests,
  imports, Streamlit compilation, 390 tests, 84.3% line coverage, 62.8% branch
  coverage, and 80.0% combined coverage. The benchmark was not included.
- Manual approved workflow: TSLA at 120/116/128 displayed and submitted 62
  shares, $7,440 capital, $248 maximum loss, and 2.00 reward/risk. The exact
  symbol, side, quantity, entry, stop, target, order type, and policy outcome
  matched one accepted Local Simulator order with ID
  `130ad853-39af-4013-8198-bb44c3aa7c44`.
- Required rejection gate failed operationally. OVERCAP at 300/295/310 did not
  violate the active preview-parity policy profile: maximum-position sizing is a
  deterministic cap in that profile, so the planner reduced the quantity from
  50 to 40 and approved it. The UI correctly displayed approved quantity `40`.
  No second order was submitted, but the required rejected manual trade was not
  produced.
- The controller stopped immediately at that gate. The supervised scanner was
  not started; no final operational export, scanner audit, authoritative final
  metrics, full reconciliation, or post-session verification was produced.
- Incident `OV-2026-07-22-004`: Low, operations/scenario selection, closed by
  disposition. Root cause was selecting a quantity-capping scenario as if it
  were a hard-rejection scenario. The production policy behaved as documented;
  this is not a product defect and no code, policy, or sizing change is required.
  A later separately authorized session must use a known hard-rejection policy
  without altering production behavior.
- Partial evidence is retained in `EVIDENCE_MANIFEST.md`. The harness failure
  message describes the expected rejected-state assertion; it must not be read
  as a presentation defect because the plan was actually approved at 40 shares.
- Stable credit: **Does not count**. The campaign remains **3 of 5 valid
  sessions**. Session 6 was not started.

## Session 6 disposition — invalid repository gate

- UTC start and stop: `2026-07-22T19:39:08Z`. The controller stopped during
  Phase 1 before verification or operational execution.
- Required identity: branch `feature/volcanes-v3.3-foundation` at
  `6a1cf97b9027ceb92242a032bca9b4bb802ff662`. Observed identity:
  `feature/dividend-events-vnext` at
  `093e1a299b2c0d0ad2c7e69f80f42b8dfcb66ee7`.
- The `v4.0.0-rc1` tag remained present at
  `ddc765b95d0663991db5aade74acbf09c66e3323`. The working tree retained the
  previously authorized documentation, validation evidence, and simulator
  state changes; no additional unstaged production-source change was observed.
- The mandatory branch and HEAD gates failed. Per the Session 6 procedure, no
  evidence-manifest rehash, JSON inventory, `make verify`, application startup,
  Local Simulator startup, manual workflow, rejection workflow, scanner
  workflow, external broker call, or post-session verification was performed.
- Incident `OV-2026-07-22-005`: Low, operations/configuration, session blocker.
  Expected behavior was to begin only from the validated corrective commit;
  observed behavior was invocation from the isolated dividend-vNext feature
  branch. No broker order or trading outcome occurred. Root cause is repository
  context selection, not a production defect. Corrective action is for the
  operator to restore the expected validation repository context only when the
  unrelated working tree can be preserved safely, before authorizing a later
  validation session.
- Sanitized failure evidence:
  `build/validation/session6-failure-20260722T193908Z.json`, SHA-256
  `4d7c60b0eb7366ab144b17171a662a73f103e64e86fb51ebd83f0764ad76387f`.
- Stable credit: **Does not count**. The campaign remains **3 of 5 valid
  sessions**. Stable is not eligible.

## Administrative evidence-governance correction — 2026-07-22

This administrative action was not an operational validation session. No
software defect was found, and no application, simulator, broker, manual, or
scanner workflow was started. Two historical manifest entries had incorrectly
treated mutable runtime paths as immutable evidence targets:
`state/simulated_broker.json` and `logs/automation_audit.jsonl`.

Exact historical copies matching the recorded hashes were recovered from the
original validation working tree. They were frozen byte-for-byte as
`build/validation/session1-simulated-broker-state-frozen.json` and
`build/validation/session1-scanner-audit-frozen.jsonl`. Both parse successfully
and match their preserved historical SHA-256 values. The original live paths
remain documented as mutable source provenance and are excluded from future
immutable-integrity enforcement; the frozen paths supersede them as the
authoritative evidence records.

No evidence is unrecoverable. The campaign remains **3 of 5 valid sessions**.
Session 7 was not started.

## Session 7 disposition

- Exact tested commit: `6a1cf97b9027ceb92242a032bca9b4bb802ff662`;
  `v4.0.0-rc1` remained at
  `ddc765b95d0663991db5aade74acbf09c66e3323`.
- Repository and evidence gates passed before execution. The dedicated worktree
  was on `feature/volcanes-v3.3-foundation`, no production or test difference
  existed, all 31 pre-existing immutable manifest entries matched SHA-256, and
  all 28 JSON plus 3 JSONL artifacts parsed.
- Pre- and post-session `make verify` passed Black, Ruff, MyPy, 17 architecture
  tests, imports, Streamlit compilation, 390 tests, 84.3% line coverage, 62.8%
  branch coverage, and 80.0% combined coverage.
- Manual approved workflow: AMD at 50/48/54 displayed and submitted 125 shares,
  $6,250 capital, $250 maximum loss, and 2.00 reward/risk. Preview and fresh
  pre-submit planning matched one accepted Local Simulator bracket order with
  ID `57a396ee-58d7-49f8-8560-34eea1aa20ea`.
- Mandatory hard rejection: BADRR7 at 50/48/53 was rejected with
  `Reward/risk 1.50 is below the required 2.00.`, displayed approved quantity
  `—`, and created no simulator order. No quantity or exposure adjustment was
  used as a rejection substitute.
- Scanner workflow: one controlled CRM signal traversed Scanner,
  `ExecutionSupervisor`, `PreviewTradeService`, `SubmitTradeService`,
  `TradePlanner`, `ExecutionPipeline`, and the Local Simulator adapter. It
  created one accepted 62-share bracket order with ID
  `920c8c5d-9942-4407-97f7-330fc62887c2`. Scanner audit contains exactly
  `scan_completed` then `paper_order_submitted` for the same order ID.
- Reconciliation: five previews partitioned into four approved plans and one
  rejection; two submissions equal two unique broker orders; eleven event
  publication attempts equal eleven publication-latency observations. Manual
  and scanner quantities, symbols, prices, stops, targets, sides, and order types
  match their plans. Drift, replay, idempotency conflict, duplicate execution,
  symbol-busy, cooldown, broker failure, and instrumentation failure counters
  are all zero. No external broker or market call occurred.
- Evidence: seven Session 7 artifacts are listed in `EVIDENCE_MANIFEST.md`.
  After registration, all 38 immutable entries match and all 34 JSON plus 4
  JSONL artifacts parse. Prior evidence remained unchanged.
- Incidents: none. Warnings are limited to the expected AppTest bare-mode
  `ScriptRunContext` warning and the documented `NullEventPublisher` durability
  limitation.
- Stable credit: **Counts as validation session 4 of 5**. Stable remains blocked
  until five valid sessions span at least seven calendar days and the remaining
  release criteria are complete.

## Stable-release decisions

| Decision | Status | Owner/date | Rationale or follow-up |
|---|---|---|---|
| Process-local idempotency and locking | Proposed: **Accept with constraints** | ADR-0008 / 2026-07-21 | Paper-only, exactly one process and replica, dedicated account, restart reconciliation, and no external submitter; final acceptance remains part of stable review |
| `NullEventPublisher` | Proposed: **Accept with constraints** | ADR-0009 / 2026-07-21 | Paper-only, supervised operation with per-session exports and broker evidence; no durable audit/replay/recovery claim; final acceptance remains part of stable review |
| v4.0 stable readiness | Five-session count complete; Stable still blocked | | Sessions 2, 3, 4, 7, and 8 supply 5 of 5 valid sessions; the seven-calendar-day span, Alpaca Paper smoke, and final infrastructure dispositions remain required |

## Session 8 disposition

- UTC session window: repository and evidence gates began at
  `2026-07-23T12:50:22Z`; final post-documentation verification completed at
  `2026-07-23T13:12:13.226437Z`. The isolated operational workflow ran from
  `2026-07-23T13:03:44.379633Z` to
  `2026-07-23T13:03:44.707997Z` (0.328 seconds).
- Repository baseline: dedicated validation worktree
  `/Users/EYUSEFF/Documents/GitHub/EduTraderAI_v4_validation`, branch
  `feature/volcanes-v3.3-foundation`, HEAD
  `6a1cf97b9027ceb92242a032bca9b4bb802ff662`, with `v4.0.0-rc1`
  unchanged at `ddc765b95d0663991db5aade74acbf09c66e3323`.
  Production, tests, configuration, dependencies, and architecture files
  matched HEAD before and after the session.
- Evidence gate: all 38 pre-existing immutable entries passed before the
  session; 34 JSON and 4 JSONL files parsed. Session 7 and both frozen Session 1
  artifacts remained unchanged. Mutable live paths remained excluded.
- Verification: pre- and post-session `make verify` both passed Black, Ruff,
  MyPy over 41 source files, 17 architecture tests, import checks, Streamlit
  compilation, and 390 tests. Coverage remained 84.3% line, 62.8% branch, and
  80.0% combined. The release gate does not include the separate performance
  benchmark, so none was run.
- Manual approval: MSFT BUY at 50/48/54 produced reward/risk 2.00, approved
  quantity 125, $6,250 capital, and $250 maximum planned loss. The fresh
  submission preview shared correlation ID
  `29ce5f63-6ba0-4f0d-8ed4-83ab9f3e3739` with the submission, and all plan
  fields matched one accepted bracket-limit simulator order,
  `09e573c5-85fb-4a16-949f-1bc5701db744`.
- Mandatory hard rejection: BADRR8 BUY at 50/48/53 was rejected by
  `RewardRiskPolicy` with
  `Reward/risk 1.50 is below the required 2.00.`, displayed approved quantity
  `—`, published the correlated preview/violation/rejection sequence, and
  created zero submissions and zero orders.
- Scanner: one controlled ORCL candidate traversed Scanner,
  `ExecutionSupervisor`, `PreviewTradeService`, `SubmitTradeService`,
  `TradePlanner`, `ExecutionPipeline`, and the Local Simulator adapter. The
  approved plan was 62 shares, $4,960 capital, and $248 maximum loss. One
  accepted bracket-limit order was recorded as
  `7ab7a0d7-b523-4c18-8fbb-e8189346e16f`. The scanner audit sequence was exactly
  `scan_completed` then `paper_order_submitted`.
- Reconciliation: five previews partitioned into four approvals and one
  rejection; one manual plus one scanner submission equalled two unique
  accepted simulator orders. Eleven event-publication attempts equalled eleven
  publication-latency observations. Submitted symbols, sides, quantities,
  prices, stops, targets, order types, and identifiers matched their plans.
  Drift, replay, conflict, duplicate execution, cooldown, symbol-busy, broker
  failure, instrumentation failure, orphan event, stale state, contradictory
  record, and supervisor deadlock results were all zero.
- Isolation: the observer recorded zero external broker calls and zero external
  market-data calls. Alpaca credentials were removed from the isolated process,
  no external adapter was active, and temporary simulator state was removed
  only after byte-identical broker and scanner-audit evidence was frozen.
- Evidence: seven new immutable Session 8 artifacts are registered in
  `EVIDENCE_MANIFEST.md`. The authoritative final export SHA-256 is
  `9c091c1c1ae0138ba1d824cf540a76719b93a4e5823c661d2ed0366ad4619cc1`;
  the observer SHA-256 is
  `26b5b7d33957735c7bb83f76a6361fd5ac16b8884b4c49fd77c540edacd6f89b`.
  The final manifest result is 45 of 45, comprising 40 JSON and 5 JSONL files.
- Incidents: none. Warnings were the expected AppTest bare-mode
  `ScriptRunContext` warning, the accepted `NullEventPublisher` durability
  limitation, and a temporary controller import-path preflight that stopped
  before application import or runtime initialization. The temporary controller
  was corrected without changing repository source, and the actual operational
  workflow ran exactly once.
- Final result: **Operational Validation Session 8: VALID**. The campaign is
  **5 of 5 valid operational sessions**, satisfying the five-session
  operational-validation requirement. This does **not** declare v4 Stable.
  Stable remains blocked by the seven-calendar-day observation span, the
  credentialed Alpaca Paper smoke test, and final infrastructure limitation
  dispositions.
