from __future__ import annotations

from datetime import datetime
import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="EduTrader AI",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


# -----------------------------
# Demo data
# -----------------------------
RANKING_DATA = [
    {"Rank": 1, "Ticker": "META", "Score": 95, "Signal": "STRONG BUY", "Price": 515.40, "RSI": 61.2, "Risk": "Medium"},
    {"Rank": 2, "Ticker": "NVDA", "Score": 95, "Signal": "STRONG BUY", "Price": 141.25, "RSI": 64.7, "Risk": "High"},
    {"Rank": 3, "Ticker": "AAPL", "Score": 85, "Signal": "BUY", "Price": 224.10, "RSI": 57.4, "Risk": "Low"},
    {"Rank": 4, "Ticker": "AMZN", "Score": 70, "Signal": "BUY", "Price": 218.70, "RSI": 55.1, "Risk": "Medium"},
    {"Rank": 5, "Ticker": "GOOGL", "Score": 50, "Signal": "HOLD", "Price": 192.35, "RSI": 49.8, "Risk": "Low"},
    {"Rank": 6, "Ticker": "MSFT", "Score": 40, "Signal": "SELL", "Price": 452.80, "RSI": 43.6, "Risk": "Medium"},
]

PRICE_HISTORY = pd.DataFrame(
    {
        "Day": pd.date_range(end=datetime.now(), periods=30, freq="D"),
        "Price": [
            490, 494, 492, 497, 501, 499, 503, 506, 508, 505,
            509, 512, 510, 514, 516, 518, 515, 519, 522, 521,
            524, 526, 523, 527, 529, 531, 528, 532, 534, 535,
        ],
    }
).set_index("Day")


def signal_label(signal: str) -> str:
    icons = {
        "STRONG BUY": "🟢",
        "BUY": "🟩",
        "HOLD": "🟡",
        "SELL": "🔴",
    }
    return f"{icons.get(signal, '⚪')} {signal}"


def recommendation_text(row: pd.Series) -> str:
    signal = row["Signal"]
    ticker = row["Ticker"]
    score = row["Score"]
    rsi = row["RSI"]
    risk = row["Risk"]

    if signal == "STRONG BUY":
        return (
            f"{ticker} is currently rated STRONG BUY with an AI score of {score}/100. "
            f"Momentum remains positive, while RSI at {rsi:.1f} is elevated but not yet extreme. "
            f"Risk is classified as {risk.lower()}, so position sizing and stop-loss discipline remain important."
        )
    if signal == "BUY":
        return (
            f"{ticker} is rated BUY with a score of {score}/100. "
            f"The setup is constructive, with RSI at {rsi:.1f}. "
            f"Consider entering only if the trade fits your portfolio risk limits."
        )
    if signal == "HOLD":
        return (
            f"{ticker} is rated HOLD with a score of {score}/100. "
            "The model does not currently identify a strong enough edge for a new position."
        )
    return (
        f"{ticker} is rated SELL with a score of {score}/100. "
        "The current setup is weak, so the model recommends avoiding a new long position."
    )


# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    st.title("📈 EduTrader AI")
    st.caption("Professional Trading Dashboard")
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

    st.caption("EduTrader AI v3.0 Preview")


ranking_df = pd.DataFrame(RANKING_DATA)
ranking_df["Signal Display"] = ranking_df["Signal"].map(signal_label)


# -----------------------------
# Dashboard
# -----------------------------
if page == "Dashboard":
    st.title("EduTrader AI Professional")
    st.caption(f"Market intelligence dashboard · {datetime.now():%A, %B %d, %Y}")
    st.divider()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Top AI Score", "95 / 100", "+5")
    col2.metric("Trade Candidates", "4", "+1")
    col3.metric("Portfolio Value", f"${account_value:,.0f}")
    col4.metric("Risk per Trade", f"{risk_per_trade:.2f}%")

    st.subheader("🏆 Top Opportunities")
    display_df = ranking_df[["Rank", "Ticker", "Score", "Signal Display", "Price", "RSI", "Risk"]].copy()
    display_df.columns = ["Rank", "Ticker", "AI Score", "Signal", "Price", "RSI", "Risk"]
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    left, right = st.columns([1.5, 1])

    with left:
        st.subheader("📊 Market Trend")
        st.line_chart(PRICE_HISTORY, use_container_width=True)

    with right:
        st.subheader("🤖 AI Recommendation")
        selected = st.selectbox("Select stock", ranking_df["Ticker"].tolist())
        selected_row = ranking_df.loc[ranking_df["Ticker"] == selected].iloc[0]

        st.metric("Current Signal", signal_label(selected_row["Signal"]))
        st.metric("AI Score", f"{selected_row['Score']} / 100")
        st.metric("Current Price", f"${selected_row['Price']:,.2f}")
        st.info(recommendation_text(selected_row))

        if selected_row["Signal"] in {"BUY", "STRONG BUY"}:
            max_risk_dollars = account_value * (risk_per_trade / 100)
            example_stop_distance = selected_row["Price"] * 0.05
            shares = int(max_risk_dollars / example_stop_distance) if example_stop_distance else 0
            st.success(
                f"Illustrative position size: {shares} shares, assuming a 5% stop distance."
            )
        else:
            st.warning("No new trade is recommended for this stock.")

    st.caption(
        "Educational prototype only. This application does not provide personalized financial advice."
    )


# -----------------------------
# Market Scanner
# -----------------------------
elif page == "Market Scanner":
    st.title("Market Scanner")
    st.caption("Rank securities by AI score, technical momentum, and risk.")

    minimum_score = st.slider("Minimum AI score", 0, 100, 50, 5)
    signals = st.multiselect(
        "Signals",
        ["STRONG BUY", "BUY", "HOLD", "SELL"],
        default=["STRONG BUY", "BUY", "HOLD", "SELL"],
    )

    filtered = ranking_df[
        (ranking_df["Score"] >= minimum_score)
        & (ranking_df["Signal"].isin(signals))
    ]

    st.dataframe(
        filtered[["Rank", "Ticker", "Score", "Signal Display", "Price", "RSI", "Risk"]],
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download scanner results",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name="edutrader_scanner_results.csv",
        mime="text/csv",
    )


# -----------------------------
# Portfolio
# -----------------------------
elif page == "Portfolio":
    st.title("Portfolio")
    st.caption("Preview of portfolio monitoring and position sizing.")

    cash = account_value * 0.35
    invested = account_value - cash
    daily_change = account_value * 0.0064

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Value", f"${account_value:,.2f}", f"${daily_change:,.2f}")
    c2.metric("Invested", f"${invested:,.2f}")
    c3.metric("Cash", f"${cash:,.2f}")

    positions = pd.DataFrame(
        [
            {"Ticker": "META", "Shares": 35, "Average Cost": 498.20, "Current Price": 515.40},
            {"Ticker": "NVDA", "Shares": 80, "Average Cost": 132.10, "Current Price": 141.25},
            {"Ticker": "AAPL", "Shares": 45, "Average Cost": 216.50, "Current Price": 224.10},
        ]
    )
    positions["Market Value"] = positions["Shares"] * positions["Current Price"]
    positions["P/L"] = (
        positions["Current Price"] - positions["Average Cost"]
    ) * positions["Shares"]

    st.dataframe(positions, use_container_width=True, hide_index=True)


# -----------------------------
# Backtesting
# -----------------------------
elif page == "Backtesting":
    st.title("Backtesting")
    st.caption("The backtesting engine will be connected in EduTrader AI v3.1.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Return", "18.4%")
    c2.metric("Win Rate", "62.5%")
    c3.metric("Max Drawdown", "-7.8%")
    c4.metric("Sharpe Ratio", "1.41")

    equity_curve = pd.DataFrame(
        {
            "Date": pd.date_range(end=datetime.now(), periods=60, freq="D"),
            "Portfolio Value": [
                100000 + (i * 290) + ((i % 7) - 3) * 140 for i in range(60)
            ],
        }
    ).set_index("Date")

    st.subheader("Equity Curve")
    st.line_chart(equity_curve, use_container_width=True)
    st.info("This page currently uses demonstration data.")


# -----------------------------
# Settings
# -----------------------------
else:
    st.title("Settings")
    st.caption("Configure portfolio and risk-management preferences.")

    st.number_input(
        "Default account value",
        min_value=1_000.0,
        value=account_value,
        step=1_000.0,
    )
    st.slider(
        "Default risk per trade",
        min_value=0.25,
        max_value=3.0,
        value=risk_per_trade,
        step=0.25,
    )
    st.checkbox("Enable trade alerts", value=False)
    st.checkbox("Enable paper-trading mode", value=True)

    if st.button("Save settings"):
        st.success("Settings saved for this session.")
