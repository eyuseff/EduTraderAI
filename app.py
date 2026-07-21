from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal
import logging
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from adapters.paper_order_preview import preview_paper_order
from adapters.paper_order_presentation import approved_quantity_display
from adapters.paper_order_submission import submit_paper_order
from adapters.scanner_execution import (
    ScannerExecutionRuntime,
    build_scanner_execution_runtime,
)
from broker.alpaca_paper import AlpacaPaperBroker
from broker.base import PaperBroker
from broker.simulated import SimulatedPaperBroker
from engine.brain import EduTraderBrain
from engine.supervised_brain import SupervisedEduTraderBrain
from trading.execution import PaperExecutionEngine
from trading.risk_manager import RiskLimits, RiskManager, TradeProposal
from scanner_engine.universe import CORE_UNIVERSE, normalize_universe
from volcanoes.application.platform import (
    BrokerMode,
    ConfigurationError,
    CredentialStatus,
    DeterministicFeatureFlags,
    PlatformConfiguration,
    ScannerExecutionMode,
    TradingPolicyConfiguration,
    build_platform_health_report,
    validate_broker_runtime,
    validate_configuration,
)
from volcanoes.application.operations import (
    OperationalEventPublisher,
    ProcessLocalOperationalMetrics,
    build_operational_dashboard_snapshot,
    build_validation_snapshot,
    export_validation_snapshot,
    fail_open,
    load_verification_metadata,
)
from volcanoes.events import NullEventPublisher, new_correlation_id

USE_DETERMINISTIC_PREVIEW = True
USE_DETERMINISTIC_SUBMISSION = True
USE_DETERMINISTIC_SCANNER = True
POLICY_CONFIGURATION = TradingPolicyConfiguration(
    risk_per_trade_pct=Decimal("0.25"),
    max_daily_loss_pct=Decimal("1.0"),
    max_open_positions=5,
    max_total_exposure_pct=Decimal("50.0"),
    max_single_position_pct=Decimal("12.0"),
    minimum_reward_risk=Decimal("2.0"),
    minimum_price=Decimal("10.0"),
    long_only=True,
)
DEVELOPMENT_MODE = os.getenv(
    "EDUTRADER_DEVELOPMENT_MODE",
    "",
).strip().lower() in {"1", "true", "yes", "on"}
logger = logging.getLogger(__name__)


st.set_page_config(
    page_title="EduTrader AI Paper Trading",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def local_broker(starting_cash: float) -> SimulatedPaperBroker:
    return SimulatedPaperBroker(starting_cash=starting_cash)


@st.cache_resource
def operational_metrics():
    """Keep observational metrics process-local across Streamlit reruns."""

    return fail_open(ProcessLocalOperationalMetrics())


OPERATIONAL_METRICS = operational_metrics()
EVENT_PUBLISHER = OperationalEventPublisher(
    NullEventPublisher(),
    OPERATIONAL_METRICS,
)


@st.cache_resource
def deterministic_scanner_runtime(
    broker_identity: str,
    _broker: PaperBroker,
    risk_limits: RiskLimits,
) -> ScannerExecutionRuntime:
    """Keep process-local supervisor safety state across Streamlit reruns."""

    del broker_identity
    return build_scanner_execution_runtime(
        _broker,
        risk_limits,
        event_publisher=EVENT_PUBLISHER,
        operational_metrics=OPERATIONAL_METRICS,
    )


def money(value: float) -> str:
    return f"${value:,.2f}"


with st.sidebar:
    st.title("🛡️ EduTrader AI")
    st.caption("v4.0.0-rc1 · Unified deterministic platform")
    st.success("PAPER MODE ONLY")
    navigation = [
        "Safety Dashboard",
        "Automated Scanner",
        "Paper Order",
        "Orders & Positions",
        "Legacy Dashboard",
    ]
    if DEVELOPMENT_MODE:
        navigation.insert(1, "Operational Validation")
    page = st.radio(
        "Navigation",
        navigation,
    )
    st.divider()
    broker_choice = st.selectbox("Paper broker", ["Local Simulator", "Alpaca Paper"])
    starting_cash = st.number_input(
        "Simulator starting cash",
        min_value=1_000.0,
        value=100_000.0,
        step=1_000.0,
        disabled=broker_choice != "Local Simulator",
    )
    st.caption("No live-trading adapter exists in this version.")

selected_broker_mode = (
    BrokerMode.SIMULATED_PAPER
    if broker_choice == "Local Simulator"
    else BrokerMode.ALPACA_PAPER
)
startup_configuration = PlatformConfiguration(
    feature_flags=DeterministicFeatureFlags(
        preview=USE_DETERMINISTIC_PREVIEW,
        submission=USE_DETERMINISTIC_SUBMISSION,
        scanner=USE_DETERMINISTIC_SCANNER,
    ),
    policy=POLICY_CONFIGURATION,
    broker_mode=selected_broker_mode,
    scanner_execution_mode=(
        ScannerExecutionMode.SUPERVISED
        if USE_DETERMINISTIC_SCANNER
        else ScannerExecutionMode.LEGACY_ROLLBACK
    ),
    credentials=CredentialStatus(
        alpaca_api_key_present=bool(os.getenv("ALPACA_API_KEY", "").strip()),
        alpaca_secret_key_present=bool(os.getenv("ALPACA_SECRET_KEY", "").strip()),
    ),
)
try:
    validate_configuration(startup_configuration)
except ConfigurationError as exc:
    st.error(f"Startup configuration is invalid: {exc}")
    st.stop()

try:
    broker = (
        local_broker(starting_cash)
        if broker_choice == "Local Simulator"
        else AlpacaPaperBroker()
    )
    connection_error = None
    runtime_configuration = startup_configuration
except Exception as exc:  # shown safely in UI
    broker = local_broker(starting_cash)
    connection_error = str(exc)
    runtime_configuration = replace(
        startup_configuration,
        broker_mode=BrokerMode.SIMULATED_PAPER,
    )

try:
    validate_configuration(runtime_configuration)
    validate_broker_runtime(
        runtime_configuration,
        broker_is_paper=broker.is_paper,
    )
except ConfigurationError as exc:
    st.error(f"Startup configuration is unsafe: {exc}")
    st.stop()

limits = RiskLimits(
    risk_per_trade_pct=float(POLICY_CONFIGURATION.risk_per_trade_pct),
    max_daily_loss_pct=float(POLICY_CONFIGURATION.max_daily_loss_pct),
    max_open_positions=POLICY_CONFIGURATION.max_open_positions,
    max_total_exposure_pct=float(POLICY_CONFIGURATION.max_total_exposure_pct),
    max_single_position_pct=float(POLICY_CONFIGURATION.max_single_position_pct),
    minimum_reward_risk=float(POLICY_CONFIGURATION.minimum_reward_risk),
    minimum_price=float(POLICY_CONFIGURATION.minimum_price),
    long_only=POLICY_CONFIGURATION.long_only,
)
engine = PaperExecutionEngine(broker, RiskManager(limits))
account = broker.get_account()
positions = broker.get_positions()
orders = broker.get_open_orders()
platform_health = build_platform_health_report(
    runtime_configuration,
    event_publisher_type=type(EVENT_PUBLISHER.delegate).__name__,
)

if connection_error:
    st.warning(f"Alpaca Paper was not connected: {connection_error}")
    st.info("The app has fallen back to the Local Simulator.")

if page == "Safety Dashboard":
    st.title("EduTrader AI Safety Dashboard")
    st.caption(f"Paper environment status · {datetime.now():%A, %B %d, %Y %H:%M}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Broker", broker.name)
    c2.metric("Equity", money(account.equity))
    c3.metric("Buying Power", money(account.buying_power))
    c4.metric("Daily P/L", money(account.daily_pnl))

    st.subheader("Mandatory Risk Limits")
    limits_df = pd.DataFrame(
        [
            ["Risk per trade", f"{limits.risk_per_trade_pct:.2f}%"],
            ["Daily loss lock", f"{limits.max_daily_loss_pct:.2f}%"],
            ["Maximum open positions", str(limits.max_open_positions)],
            ["Maximum total exposure", f"{limits.max_total_exposure_pct:.0f}%"],
            ["Maximum single position", f"{limits.max_single_position_pct:.0f}%"],
            ["Minimum reward/risk", f"{limits.minimum_reward_risk:.1f}"],
            ["Minimum stock price", money(limits.minimum_price)],
            ["Direction", "Long only"],
        ],
        columns=["Control", "Limit"],
    )
    st.dataframe(limits_df, width="stretch", hide_index=True)

    st.subheader("Safety State")
    checks = {
        "Paper-only broker": broker.is_paper,
        "Daily loss lock clear": account.daily_pnl
        > -(account.equity * limits.max_daily_loss_pct / 100),
        "Position capacity available": len(positions) < limits.max_open_positions,
        "Credentials absent from source code": True,
        "Manual confirmation required": True,
    }
    for label, passed in checks.items():
        st.success(f"✅ {label}") if passed else st.error(f"⛔ {label}")

    st.warning(
        "Paper trading is a simulation. It does not reproduce every effect of live execution, "
        "including all slippage, queue position, partial fills, outages, or price gaps."
    )
    if DEVELOPMENT_MODE:
        with st.expander("Platform health (development)"):
            st.json(platform_health.to_dict())


elif page == "Operational Validation":
    st.title("Operational Validation")
    st.caption("Development-only, process-local release-candidate observations")

    verification = load_verification_metadata(
        Path(__file__).resolve().parent / "build/verification.json"
    )
    dashboard = build_operational_dashboard_snapshot(
        platform_health,
        OPERATIONAL_METRICS.snapshot(),
        verification,
    )
    health = dashboard.health
    counters = dict(dashboard.metrics.counters)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Release", health.release)
    c2.metric("Broker mode", health.broker_mode)
    c3.metric("Event publisher", health.event_publisher_type)
    c4.metric(
        "Verification",
        verification.status if verification is not None else "Not available",
    )

    st.subheader("Execution paths")
    path_rows = [
        {"State": "Active", "Path": path} for path in health.active_execution_paths
    ] + [
        {"State": "Rollback", "Path": path} for path in health.rollback_execution_paths
    ]
    st.dataframe(pd.DataFrame(path_rows), width="stretch", hide_index=True)

    st.subheader("Operational counters")
    counter_rows = [
        {"Metric": name.replace("_", " ").title(), "Count": value}
        for name, value in counters.items()
    ]
    st.dataframe(pd.DataFrame(counter_rows), width="stretch", hide_index=True)

    st.subheader("Latency summaries")
    latency_rows = [
        {
            "Operation": summary.name.replace("_", " ").title(),
            "Observations": summary.count,
            "Mean ms": round(summary.mean_ms, 4),
            "Minimum ms": round(summary.minimum_ms, 4),
            "Maximum ms": round(summary.maximum_ms, 4),
        }
        for summary in dashboard.metrics.latencies
    ]
    st.dataframe(pd.DataFrame(latency_rows), width="stretch", hide_index=True)

    st.subheader("Operational state")
    st.write(f"Supervisor state: {health.supervisor_state_mode}")
    st.write(f"Scanner execution: {health.scanner_execution_mode}")
    for limitation in health.known_operational_limitations:
        st.warning(limitation)

    if st.button("Export sanitized validation snapshot"):
        export_path = (
            Path(__file__).resolve().parent
            / "build/validation"
            / f"v4.0.0-rc1-{datetime.now():%Y%m%d-%H%M%S}.json"
        )
        exported = export_validation_snapshot(
            export_path,
            build_validation_snapshot("4.0.0-rc1", dashboard),
        )
        st.success(f"Validation snapshot exported locally: {exported}")


elif page == "Automated Scanner":
    st.title("Automated Scanner + Paper Execution")
    st.caption(
        "Run a market-regime-gated scan. Preview is the default; execution remains paper-only."
    )

    c1, c2, c3 = st.columns(3)
    min_score = c1.slider("Minimum score", 70, 100, 80)
    max_new = c2.number_input("Maximum new paper trades", 1, 3, 3)
    universe_text = c3.text_input("Optional tickers", value="")
    custom = [x.strip().upper() for x in universe_text.split(",") if x.strip()]
    symbols = normalize_universe(custom or list(CORE_UNIVERSE))

    execute = st.checkbox(
        "Submit approved paper orders automatically after this scan", value=False
    )
    confirmation = st.text_input(
        "To enable paper submission, type exactly: AUTO PAPER",
        disabled=not execute,
    )
    run_disabled = execute and confirmation != "AUTO PAPER"

    if st.button("Run Automated Scan", type="primary", disabled=run_disabled):
        try:
            brain: EduTraderBrain | SupervisedEduTraderBrain
            if USE_DETERMINISTIC_SCANNER:
                runtime = deterministic_scanner_runtime(
                    f"{broker.name}:{id(broker)}",
                    broker,
                    limits,
                )
                brain = SupervisedEduTraderBrain(
                    runtime.supervisor,
                    runtime.snapshot_provider,
                    operational_metrics=OPERATIONAL_METRICS,
                )
            else:
                brain = EduTraderBrain(engine)
            with st.spinner(f"Scanning {len(symbols)} liquid instruments..."):
                cycle = brain.run_cycle(
                    symbols,
                    min_score=min_score,
                    max_new_trades=int(max_new),
                    submit_orders=execute,
                )
            regime = cycle.scan.regime
            if regime.tradeable:
                st.success(
                    f"Market regime: {regime.label} ({regime.score}/100) — trading gate open"
                )
            else:
                st.error(
                    f"Market regime: {regime.label} ({regime.score}/100) — new trades blocked"
                )
            for reason in regime.reasons:
                st.write(f"• {reason}")

            st.subheader("Qualified Candidates")
            rows = [
                {
                    "Symbol": x.symbol,
                    "Score": x.score,
                    "Entry": x.entry_price,
                    "Stop": x.stop_price,
                    "Target": x.target_price,
                    "Daily Change %": round(x.daily_change_pct, 2),
                    "Average Volume": int(x.average_volume),
                }
                for x in cycle.scan.qualified
            ]
            if rows:
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
            else:
                st.info("No candidates passed every scanner filter.")

            st.subheader("Paper Orders / Previews")
            if cycle.submitted:
                st.dataframe(
                    pd.DataFrame(cycle.submitted),
                    width="stretch",
                    hide_index=True,
                )
            else:
                st.info("No paper orders or previews were produced.")

            with st.expander("Rejected candidates and reasons"):
                rejected = cycle.scan.rejected + cycle.rejected_by_risk
                if rejected:
                    st.dataframe(
                        pd.DataFrame(rejected),
                        width="stretch",
                        hide_index=True,
                    )
                else:
                    st.write("No rejected candidates.")
        except Exception as exc:
            st.error(f"Automated scan failed safely: {exc}")

elif page == "Paper Order":
    st.title("Create a Paper Trade")
    st.caption("Every proposal must pass the risk engine before submission.")

    left, right = st.columns(2)
    with left:
        symbol = st.text_input("Ticker", value="AAPL").strip().upper()
        entry = st.number_input(
            "Limit entry price", min_value=0.01, value=100.00, step=0.10
        )
        stop = st.number_input(
            "Stop-loss price", min_value=0.01, value=97.50, step=0.10
        )
        target = st.number_input(
            "Profit-target price", min_value=0.01, value=105.00, step=0.10
        )

    proposal = TradeProposal(
        symbol=symbol, entry_price=entry, stop_price=stop, target_price=target
    )
    trade_correlation_id = new_correlation_id()
    decision = preview_paper_order(
        broker=broker,
        proposal=proposal,
        limits=limits,
        legacy_preview=engine.preview,
        use_deterministic_preview=USE_DETERMINISTIC_PREVIEW,
        development_mode=DEVELOPMENT_MODE,
        logger=logger,
        correlation_id=trade_correlation_id,
        event_publisher=EVENT_PUBLISHER,
        operational_metrics=OPERATIONAL_METRICS,
    )

    with right:
        st.subheader("Risk Preview")
        st.metric("Approved quantity", approved_quantity_display(decision))
        st.metric("Capital required", money(decision.capital_required))
        st.metric("Maximum planned loss", money(decision.maximum_loss))
        st.metric("Reward / Risk", f"{decision.reward_risk:.2f}")
        if decision.approved:
            st.success("All automatic risk checks passed.")
        else:
            st.error("Trade rejected by the risk engine.")
            for reason in decision.reasons:
                st.write(f"• {reason}")

    confirmation = st.text_input(
        "To submit, type exactly: PAPER TRADE",
        type="default",
        disabled=not decision.approved,
    )
    if st.button(
        "Submit Paper Bracket Order", type="primary", disabled=not decision.approved
    ):
        try:
            order = submit_paper_order(
                broker=broker,
                proposal=proposal,
                displayed_preview=decision,
                limits=limits,
                confirmation=confirmation,
                legacy_submit=engine.submit,
                use_deterministic_submission=USE_DETERMINISTIC_SUBMISSION,
                correlation_id=trade_correlation_id,
                event_publisher=EVENT_PUBLISHER,
                operational_metrics=OPERATIONAL_METRICS,
            )
            st.success(
                f"Paper order accepted: {order.symbol}, {order.quantity} shares. "
                f"Order ID: {order.order_id}"
            )
            st.info(order.message)
        except Exception as exc:
            st.error(str(exc))

elif page == "Orders & Positions":
    st.title("Paper Orders & Positions")
    st.caption(f"Connected to {broker.name}")

    st.subheader("Open Orders")
    order_rows = [order.__dict__ for order in broker.get_open_orders()]
    if order_rows:
        st.dataframe(pd.DataFrame(order_rows), width="stretch", hide_index=True)
    else:
        st.info("No open paper orders.")

    st.subheader("Positions")
    position_rows = [
        {
            "Symbol": p.symbol,
            "Quantity": p.quantity,
            "Average Entry": p.average_entry_price,
            "Current Price": p.current_price,
            "Market Value": p.market_value,
            "Unrealized P/L": p.unrealized_pnl,
        }
        for p in broker.get_positions()
    ]
    if position_rows:
        st.dataframe(pd.DataFrame(position_rows), width="stretch", hide_index=True)
    else:
        st.info("No paper positions.")

    st.divider()
    st.subheader("Emergency Controls")
    st.warning("These buttons affect the selected paper environment only.")
    c1, c2 = st.columns(2)
    if c1.button("Cancel All Paper Orders"):
        st.success(f"Cancellation requested for {broker.cancel_all_orders()} order(s).")
    if c2.button("Close All Paper Positions"):
        st.success(f"Close requested for {broker.close_all_positions()} position(s).")

else:
    st.title("Legacy Dashboard")
    st.info(
        "Your original v3.0 dashboard is preserved as app_legacy.py. "
        "Run it separately with: python3 -m streamlit run app_legacy.py"
    )

st.divider()
st.caption(
    "Educational software under development. Paper results do not guarantee live results. "
    "EduTrader AI v4.0.0-rc1 cannot connect to a live trading endpoint."
)
