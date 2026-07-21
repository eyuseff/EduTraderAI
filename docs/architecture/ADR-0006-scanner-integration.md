# ADR-0006: Scanner Integration Through the Execution Supervisor

- Status: Accepted
- Date: 2026-07-20

## Context

The active Streamlit automation path previously passed each qualified scanner
signal to `EduTraderBrain`. That legacy orchestrator created a `TradeProposal`,
called `PaperExecutionEngine.preview()` for sizing and risk, made the execution
decision, and then called `PaperExecutionEngine.submit()`. Those responsibilities
duplicated the deterministic planning and execution platform now used by manual
Paper Orders.

The scanner's durable responsibility is signal production: market-data loading,
market-regime classification, candidate scoring, liquidity filtering, and the
entry, stop, and target suggested by the strategy. It must not independently
size a position, approve risk, check execution duplicates, or submit an order.

## Decision

The default scanner path converts every qualified `StrategySignal` into an
immutable `ExecutionRequest` with `AUTOMATION` source. `ExecutionSupervisor` is
the sole execution gatekeeper and invokes the existing deterministic preview and
submission services, which share one `TradePlanner`.

```text
Streamlit Automated Scanner page
              |
              v
scanner_engine (signals only)
              |
              v
SupervisedEduTraderBrain (signal translation)
              |
              v
ExecutionRequest --> ExecutionSupervisor
                         |
                         +--> PreviewTradeService --> TradePlanner
                         |
                         +--> SubmitTradeService --> ExecutionPipeline
                                                        |
                                                        v
                                             paper broker adapter
```

`SupervisedEduTraderBrain` imports the application supervisor boundary and does
not import broker, planner, risk-manager, execution-pipeline, adapter, or trading
policy modules. Concrete broker snapshot and order translation remains in
`adapters/scanner_execution.py`.

Preview-only scanner runs are represented explicitly by `ExecutionMode` and
still pass through supervisor admission and deterministic preview. They never
invoke submission. Submission mode follows the complete supervisor path.

## Idempotency, symbol serialization, and cooldown

Each signal request receives a new correlation ID. Its idempotency key is a
deterministic SHA-256 digest of the scanner source, execution mode, normalized
symbol, entry, stop, and target. Repeated identical scans therefore replay or
skip the completed result without submitting another order, while preview-only
and submission requests remain distinct.

The long-lived supervisor retains process-local idempotency, duplicate-trade,
cooldown, and active-symbol state. Streamlit caches that runtime per active
broker identity and risk configuration, so normal UI reruns do not erase safety
state. A fresh immutable broker snapshot is captured for each admitted scanner
candidate. Supervisor events and all service events carry the same correlation
ID from preview through broker submission.

The cooldown policy is composed explicitly. Its default window remains zero to
preserve current scanner timing; deployments can configure a non-zero window
without moving orchestration rules back into the scanner.

## Preserved outer behavior

The existing scan schedule (one scan per button action), universe normalization,
candidate ordering and cap, spinner, confirmation phrase, UI labels, result
tables, audit event names, and paper-only broker guarantee are unchanged. The
new adapter validates paper mode before constructing the deterministic runtime.

The UI-compatible `TradingCycleReport` is shared by both implementations.
Supervisor skips and deterministic policy rejections are presented through the
existing rejected-candidates table and `risk_rejected` audit record.

## Rollback

`USE_DETERMINISTIC_SCANNER = True` selects the supervised implementation by
default. Setting it to `False` constructs the original `EduTraderBrain` with the
unchanged `PaperExecutionEngine`, immediately restoring the previous scanner
preview and submission path. The legacy implementation is retained only for
this temporary operational rollback.

## Consequences and deferred infrastructure

- Scanner automation and manual Paper Orders now share deterministic planning,
  submission, policies, and operational events.
- The scanner no longer contains sizing, risk approval, duplicate-order, or
  broker-submission decisions in its default path.
- Durable event storage, restart-safe idempotency, and distributed symbol locks
  remain deferred. Current supervisor state is process-local.
- An authoritative market-state adapter remains deferred; scanner regime state
  is still a signal-generation concern, not the supervisor market-state stub.
- External schedulers and any non-Streamlit automation entry points have not yet
  been composed with a durable supervisor runtime.
- The legacy `EduTraderBrain` and `PaperExecutionEngine` scanner path remains
  intentionally available only while the rollback flag exists.
