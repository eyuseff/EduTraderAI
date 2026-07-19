from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from config import APP_NAME, WATCHLIST
from position_sizing import PositionSizingEngine
from risk import RiskEngine
from scanner import MarketScanner
from strategy import StrategyEngine


st.set_page_config(
    page_title=f"{APP_NAME} 3.1",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

TRADEABLE = {"BUY", "STRONG BUY"}


def signal_icon(signal: str) -> str:
    icons = {
        "STRONG BUY": "🟢",
        "BUY": "🟩",
        "HOLD": "🟡",
        "SELL": "🟥",
        "STRONG SELL": "🔴",
    }
    return f"{icons.get(signal, '⚪')} {signal}"


def risk_level(atr: float, price: float) -> str:
    if price <= 0:
        return "Unknown"
    atr_pct = atr / price * 100
    if atr_pct < 2.5:
        return "Low"
    if atr_pct < 5.0:
        return "Medium"
    return "High"


@st.cache_data(ttl=900, show_spinner=False)
def run_live_scan() -> pd.DataFrame:
    scanner = MarketScanner()
    strategy = StrategyEngine()
    risk_engine = RiskEngine()

    rows: list[dict[str, Any]] = []
    for stock in scanner.scan():
        result = strategy.evaluate(stock)
        risk = risk_engine.calculate(stock)
        rows.append(
            {
                "Ticker": stock["Symbol"],
                "Price": stock["Price"],
                "Score": result.score,
                "Signal": result.recommendation,
                "RSI": stock["RSI"],
                "EMA20": stock["EMA20"],
                "EMA50": stock["EMA50"],
                "SMA200": stock["SMA200"],
                "MACD": stock["MACD"],
                "ATR": stock["ATR"],
                "Risk": risk_level(stock["ATR"], stock["Price"]),
                "Entry": risk.entry,
                "Stop Loss": risk.stop_loss,
                "Target": risk.target,
                "Risk/Reward": risk.risk_reward,
                "Reasons": result.reasons,
            }
        )

    if not rows:
        return pd.DataFrame()

    frame = pd.DataFrame(rows).sort_values(
        ["Score", "Ticker"], ascending=[False, True]
    )
    frame.insert(0, "Rank", range(1, len(frame) + 1))
    return frame.reset_index(drop=True)


@st.cache_data(ttl=900, show_spinner=False)
def load_history(symbol: str, period: str = "6mo") -> pd.DataFrame:
    data = yf.download(
        symbol,
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    if data.empty:
        return data

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    return data.dropna(subset=["Open", "High", "Low", "Close"])


def candlestick_chart(history: pd.DataFrame, symbol: str) -> go.Figure:
    figure = go.Figure()
    figure.add_trace(
        go.Candlestick(
            x=history.index,
            open=history["Open"],
            high=history["High"],
            low=history["Low"],
            close=history["Close"],
            name=symbol,
        )
    )

    close = history["Close"]
    figure.add_trace(
        go.Scatter(
            x=history.index,
            y=close.rolling(20).mean(),
            mode="lines",
            name="SMA 20",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=history.index,
            y=close.rolling(50).mean(),
            mode="lines",
            name="SMA 50",
        )
    )
    figure.update_layout(
        title=f"{symbol} price history",
        height=520,
        margin=dict(l=10, r=10, t=55, b=10),
        xaxis_rangeslider_visible=False,
        legend_orientation="h",
    )
    return figure


def explanation(row: pd.Series) -> str:
    reasons = row.get("Reasons", [])
    reason_text = " ".join(f"• {reason}" for reason in reasons)
    return (
        f"{row['Ticker']} is rated {row['Signal']} with a score of "
        f"{int(row['Score'])}/100. {reason_text}"
    )


with st.sidebar:
    st.title("📈 EduTrader AI")
    st.caption("Live Market Intelligence")
    st.divider()

    page = st.radio(
        "Navigation",
        ["Dashboard", "Market Scanner", "Portfolio", "Backtesting", "Settings"],
    )

    st.divider()
    account_value = st.number_input(
        "Portfolio value (USD)",
        min_value=1_000.0,
        value=100_000.0,
        step=1_000.0,
    )
    risk_per_trade = st.slider(
        "Risk per trade",
        min_value=0.25,
        max_value=3.0,
        value=1.0,
        step=0.25,
        format="%.2f%%",
    )

    if st.button("🔄 Refresh live data", width="stretch"):
        run_live_scan.clear()
        load_history.clear()
        st.rerun()

    st.caption("EduTrader AI v3.1")


with st.spinner("Downloading market data and running the strategy engine..."):
    scan_df = run_live_scan()

if scan_df.empty:
    st.error(
        "No market data was returned. Check your internet connection and try Refresh live data."
    )
    st.stop()

scan_df["Signal Display"] = scan_df["Signal"].map(signal_icon)


if page == "Dashboard":
    st.title("EduTrader AI Professional")
    st.caption(f"Live dashboard · {datetime.now():%A, %B %d, %Y at %H:%M}")
    st.divider()

    top_score = int(scan_df["Score"].max())
    candidates = int(scan_df["Signal"].isin(TRADEABLE).sum())
    leader = str(scan_df.iloc[0]["Ticker"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Top AI Score", f"{top_score} / 100")
    c2.metric("Trade Candidates", str(candidates))
    c3.metric("Current Leader", leader)
    c4.metric("Portfolio Value", f"${account_value:,.0f}")

    st.subheader("🏆 Live Ranking")
    table = scan_df[
        ["Rank", "Ticker", "Score", "Signal Display", "Price", "RSI", "Risk"]
    ].copy()
    table.columns = ["Rank", "Ticker", "AI Score", "Signal", "Price", "RSI", "Risk"]
    st.dataframe(table, width="stretch", hide_index=True)

    selected = st.selectbox("Analyze stock", scan_df["Ticker"].tolist())
    row = scan_df.loc[scan_df["Ticker"] == selected].iloc[0]
    history = load_history(selected)

    left, right = st.columns([1.65, 1])
    with left:
        st.subheader("📊 Interactive Chart")
        if history.empty:
            st.warning("Price history is temporarily unavailable.")
        else:
            st.plotly_chart(candlestick_chart(history, selected), width="stretch")

    with right:
        st.subheader("🤖 Strategy Analysis")
        m1, m2 = st.columns(2)
        m1.metric("Signal", signal_icon(str(row["Signal"])))
        m2.metric("AI Score", f"{int(row['Score'])}/100")
        st.metric("Live Price", f"${float(row['Price']):,.2f}")
        st.info(explanation(row))

        st.subheader("Risk Plan")
        r1, r2, r3 = st.columns(3)
        r1.metric("Entry", f"${float(row['Entry']):,.2f}")
        r2.metric("Stop", f"${float(row['Stop Loss']):,.2f}")
        r3.metric("Target", f"${float(row['Target']):,.2f}")

        if row["Signal"] in TRADEABLE:
            sizing = PositionSizingEngine(
                account_balance=account_value,
                risk_percentage=risk_per_trade,
            ).calculate(
                entry_price=float(row["Entry"]),
                stop_loss=float(row["Stop Loss"]),
                target_price=float(row["Target"]),
            )
            st.success(
                f"Trade eligible: {sizing.shares} shares · "
                f"Capital required ${sizing.capital_required:,.2f} · "
                f"Maximum modeled loss ${sizing.actual_loss:,.2f}"
            )
        else:
            st.warning("NO TRADE: the strategy does not recommend a new long position.")

elif page == "Market Scanner":
    st.title("Live Market Scanner")
    st.caption("Yahoo Finance data evaluated by your existing EduTrader strategy engine.")

    minimum_score = st.slider("Minimum score", 0, 100, 0, 5)
    selected_signals = st.multiselect(
        "Signals",
        ["STRONG BUY", "BUY", "HOLD", "SELL", "STRONG SELL"],
        default=["STRONG BUY", "BUY", "HOLD", "SELL", "STRONG SELL"],
    )
    filtered = scan_df[
        (scan_df["Score"] >= minimum_score)
        & (scan_df["Signal"].isin(selected_signals))
    ]

    st.dataframe(
        filtered[
            [
                "Rank", "Ticker", "Score", "Signal Display", "Price", "RSI",
                "EMA20", "EMA50", "SMA200", "MACD", "ATR", "Risk",
            ]
        ],
        width="stretch",
        hide_index=True,
    )
    st.download_button(
        "Download scanner results",
        data=filtered.drop(columns=["Reasons", "Signal Display"]).to_csv(index=False),
        file_name="edutrader_live_scan.csv",
        mime="text/csv",
    )

elif page == "Portfolio":
    st.title("Portfolio & Position Sizing")
    st.caption("Risk-controlled position plans for current trade candidates.")

    plans: list[dict[str, Any]] = []
    for _, row in scan_df.iterrows():
        if row["Signal"] not in TRADEABLE:
            continue
        sizing = PositionSizingEngine(account_value, risk_per_trade).calculate(
            float(row["Entry"]), float(row["Stop Loss"]), float(row["Target"])
        )
        plans.append(
            {
                "Ticker": row["Ticker"],
                "Signal": row["Signal"],
                "Shares": sizing.shares,
                "Entry": row["Entry"],
                "Stop Loss": row["Stop Loss"],
                "Target": row["Target"],
                "Capital Required": sizing.capital_required,
                "Maximum Loss": sizing.actual_loss,
                "Estimated Profit": sizing.estimated_profit,
            }
        )

    if plans:
        st.dataframe(pd.DataFrame(plans), width="stretch", hide_index=True)
    else:
        st.info("There are no trade-eligible stocks in the current scan.")

elif page == "Backtesting":
    st.title("Backtesting")
    st.info(
        "The live dashboard is complete. The historical execution engine and equity curve "
        "will be connected in EduTrader AI v3.2."
    )

else:
    st.title("Settings")
    st.write("Current watchlist:", ", ".join(WATCHLIST))
    st.write(f"Portfolio value: ${account_value:,.2f}")
    st.write(f"Risk per trade: {risk_per_trade:.2f}%")
    st.caption("Edit WATCHLIST in config.py to add or remove symbols.")

st.divider()
st.caption(
    "Educational software only. Market data may be delayed. This is not personalized financial advice."
)
