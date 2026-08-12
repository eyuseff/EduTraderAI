# EduTraderAI v4.0.0 Alpaca Paper Smoke Test

> Document status: post-execution qualification review  
> Evidence artifact: `build/validation/alpaca-paper-smoke-20260728T203604Z.json`  
> Classification: **PASS WITH ACCEPTED LIMITATION**

This record documents the operator-reported Alpaca Paper broker lifecycle
without performing any additional broker interaction during evidence
finalization. It does not authorize live trading and does not declare
EduTraderAI v4 Stable.

## Repository Identity

| Item | Value |
|---|---|
| Repository | `/Users/EYUSEFF/Documents/GitHub/EduTraderAI_v4_validation` |
| Branch | `feature/volcanes-v3.3-foundation` |
| HEAD | `6a1cf97b9027ceb92242a032bca9b4bb802ff662` |
| RC tag | `v4.0.0-rc1` |
| RC tag target | `ddc765b95d0663991db5aade74acbf09c66e3323` |

## Paper Environment

Operator-reported facts:

- Environment: Alpaca Paper Trading.
- No real money was used.
- Paper endpoint previously authenticated successfully.
- Account status was previously confirmed `ACTIVE`.
- `trading_blocked` was previously confirmed `FALSE`.
- `account_blocked` was previously confirmed `FALSE`.
- No live order occurred.

No API key, secret key, authorization header, account number, balance, buying
power, portfolio value, or personal information is recorded in this document or
the evidence artifact.

## Application Workflow

Operator-reported facts:

- Broker selected: Alpaca Paper.
- Workflow: EduTraderAI Paper Order.
- Exact manual confirmation entered: `PAPER TRADE`.
- Automatic risk checks passed.
- Reward/risk: `2.00`.

## Submitted Paper Order

| Field | Value |
|---|---|
| Symbol | `LLY` |
| Side | `BUY` |
| Quantity | 100 shares |
| Order type | `DAY bracket-limit` |
| Entry limit | `100.00 USD` |
| Stop loss | `97.50 USD` |
| Profit target | `105.00 USD` |
| Capital shown by application | `10,000.00 USD` |
| Maximum planned loss shown | `250.00 USD` |
| Broker order identifier | `f1d2c8a4-4e97-4722-a10e-a363eef2b336` |

Broker acknowledgment was reported as received. Initial broker status was
reported as `accepted`.

## Broker Lifecycle

Operator-reported facts:

- Filled quantity: `0`.
- Average fill price: none.
- The order remained open before cancellation.
- The order was cancelled through Alpaca Paper.
- Final open-order review showed no open orders.
- No position was created.
- No live order occurred.

## Evidence Gaps

The following were not available as local artifacts during evidence
finalization and are therefore recorded as `NOT EVIDENCED` in the JSON package:

- Exact UTC execution window.
- Application audit-event sequence.
- Exact account-read request count.
- Replay-event count.
- Reconciliation-drift count beyond the operator-reported broker lifecycle.
- Unhandled broker-failure count.

## Deviation

The controlled test specified a one-share maximum, but the existing risk engine
approved and submitted 100 shares. The limit order was materially below the
observed market price, remained unfilled, and was successfully cancelled.

Safety consequence:

- No fill occurred.
- No position was created.
- The order was cancelled.
- No open orders remained.

The broker integration lifecycle passed, but deterministic one-share smoke-test
sizing was not demonstrated.

## Post-Test Engineering Verification

Post-test `make verify` passed:

- Black formatting check: pass; 50 files unchanged.
- Ruff static analysis: pass.
- MyPy deterministic boundary: pass; 41 source files.
- Architecture dependency tests: pass; 17 tests.
- Import and bytecode smoke checks: pass.
- Streamlit entry-point compilation: pass.
- Full pytest suite: 390 passed, 0 failed.
- Line coverage: 84.3%.
- Branch coverage: 62.8%.
- Combined coverage: 80.0%.

## Classification

**PASS WITH ACCEPTED LIMITATION**

Accepted limitation:

The controlled test specified a one-share maximum, but the existing risk engine
approved and submitted 100 shares. The limit order was materially below the
observed market price, remained unfilled, and was successfully cancelled. The
broker integration lifecycle passed, but deterministic one-share smoke-test
sizing was not demonstrated.

Do not classify this test as an unconditional pass.

## Release Recommendation

Overall recommendation remains:

**EXTEND VALIDATION**

Remaining gates:

1. Performance-baseline review.
2. Formal disposition of process-local coordination.
3. Formal disposition of `NullEventPublisher`.
4. Final GO / NO-GO release review.

## Non-Blocking Follow-Up Recommendation

After the release freeze, consider implementing a deterministic Paper
smoke-test mode that:

- remains Paper-only;
- forces quantity to exactly one share;
- uses a non-marketable limit;
- preserves risk and approval checks;
- automatically retrieves status;
- automatically cancels after acknowledgment; and
- produces redacted immutable evidence.

Do not implement this feature during the current release freeze.
