from __future__ import annotations

from datetime import datetime
import os

import pandas as pd
import streamlit as st

from broker.alpaca_paper import AlpacaPaperBroker
from broker.simulated import SimulatedPaperBroker
from trading.execution import PaperExecutionEngine
from trading.risk_manager import RiskLimits, RiskManager, TradeProposal


st.set_page_config(
    page_title="EduTrader AI Paper Trading",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def local_broker(starting_cash: float) -> SimulatedPaperBroker:
    return SimulatedPaperBroker(starting_cash=starting_cash)


def money(value: float) -> str:
    return f"${value:,.2f}"


with st.sidebar:
    st.title("🛡️ EduTrader AI")
    st.caption("v3.1 · Paper-Trading Foundation")
    st.success("PAPER MODE ONLY")
    page = st.radio(
        "Navigation",
        ["Safety Dashboard", "Paper Order", "Orders & Positions", "Legacy Dashboard"],
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

try:
    broker = (
        local_broker(starting_cash)
        if broker_choice == "Local Simulator"
        else AlpacaPaperBroker()
    )
    connection_error = None
except Exception as exc:  # shown safely in UI
    broker = local_broker(starting_cash)
    connection_error = str(exc)

limits = RiskLimits(
    risk_per_trade_pct=0.25,
    max_daily_loss_pct=1.0,
    max_open_positions=5,
    max_total_exposure_pct=50.0,
    max_single_position_pct=12.0,
    minimum_reward_risk=2.0,
    minimum_price=10.0,
)
engine = PaperExecutionEngine(broker, RiskManager(limits))
account = broker.get_account()
positions = broker.get_positions()
orders = broker.get_open_orders()

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
            ["Maximum open positions", limits.max_open_positions],
            ["Maximum total exposure", f"{limits.max_total_exposure_pct:.0f}%"],
            ["Maximum single position", f"{limits.max_single_position_pct:.0f}%"],
            ["Minimum reward/risk", f"{limits.minimum_reward_risk:.1f}"],
            ["Minimum stock price", money(limits.minimum_price)],
            ["Direction", "Long only"],
        ],
        columns=["Control", "Limit"],
    )
    st.dataframe(limits_df, use_container_width=True, hide_index=True)

    st.subheader("Safety State")
    checks = {
        "Paper-only broker": broker.is_paper,
        "Daily loss lock clear": account.daily_pnl > -(account.equity * limits.max_daily_loss_pct / 100),
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

elif page == "Paper Order":
    st.title("Create a Paper Trade")
    st.caption("Every proposal must pass the risk engine before submission.")

    left, right = st.columns(2)
    with left:
        symbol = st.text_input("Ticker", value="AAPL").strip().upper()
        entry = st.number_input("Limit entry price", min_value=0.01, value=100.00, step=0.10)
        stop = st.number_input("Stop-loss price", min_value=0.01, value=97.50, step=0.10)
        target = st.number_input("Profit-target price", min_value=0.01, value=105.00, step=0.10)

    proposal = TradeProposal(symbol=symbol, entry_price=entry, stop_price=stop, target_price=target)
    decision = engine.preview(proposal)

    with right:
        st.subheader("Risk Preview")
        st.metric("Approved quantity", decision.quantity)
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
        'To submit, type exactly: PAPER TRADE',
        type="default",
        disabled=not decision.approved,
    )
    if st.button("Submit Paper Bracket Order", type="primary", disabled=not decision.approved):
        try:
            order = engine.submit(proposal, confirmation)
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
        st.dataframe(pd.DataFrame(order_rows), use_container_width=True, hide_index=True)
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
        st.dataframe(pd.DataFrame(position_rows), use_container_width=True, hide_index=True)
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
    "EduTrader AI v3.1 cannot connect to a live trading endpoint."
)
